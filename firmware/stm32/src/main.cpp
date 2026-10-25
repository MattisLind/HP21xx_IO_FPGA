#include <Arduino.h>

// DevEBox STM32F4XX-M: 8 MHz HSE -> 168 MHz core / 48 MHz USB.
extern "C" void SystemClock_Config(void) {
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);
  RCC_OscInitTypeDef osc = {};
  osc.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  osc.HSEState = RCC_HSE_ON;
  osc.PLL.PLLState = RCC_PLL_ON;
  osc.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  osc.PLL.PLLM = 8;
  osc.PLL.PLLN = 336;
  osc.PLL.PLLP = RCC_PLLP_DIV2;
  osc.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&osc) != HAL_OK) Error_Handler();
  RCC_ClkInitTypeDef clock = {};
  clock.ClockType = RCC_CLOCKTYPE_SYSCLK | RCC_CLOCKTYPE_HCLK |
                   RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  clock.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  clock.AHBCLKDivider = RCC_SYSCLK_DIV1;
  clock.APB1CLKDivider = RCC_HCLK_DIV4;
  clock.APB2CLKDivider = RCC_HCLK_DIV2;
  if (HAL_RCC_ClockConfig(&clock, FLASH_LATENCY_5) != HAL_OK) Error_Handler();
}

static void fsmc_init() {
  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();
  __HAL_RCC_GPIOE_CLK_ENABLE();
  __HAL_RCC_FSMC_CLK_ENABLE();
  GPIO_InitTypeDef gpio = {};
  gpio.Mode = GPIO_MODE_AF_PP;
  gpio.Pull = GPIO_PULLUP;
  gpio.Speed = GPIO_SPEED_FREQ_HIGH;
  gpio.Alternate = GPIO_AF12_FSMC;
  // D0..3, D13..15, NOE, NWE. NE is not wired; AD is multiplexed.
  gpio.Pin = GPIO_PIN_0 | GPIO_PIN_1 | GPIO_PIN_4 | GPIO_PIN_5 |
             GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_14 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOD, &gpio);
  gpio.Pin = GPIO_PIN_7 | GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 |
             GPIO_PIN_11 | GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;
  HAL_GPIO_Init(GPIOE, &gpio);
  gpio.Pin = GPIO_PIN_7;  // NADV
  HAL_GPIO_Init(GPIOB, &gpio);
  // Asynchronous multiplexed PSRAM, 16 bit, mode A; no WAIT/burst/byte access.
  FSMC_Bank1->BTCR[0] = FSMC_BCR1_MUXEN | FSMC_BCR1_MTYP_0 |
                       FSMC_BCR1_MWID_0 | FSMC_BCR1_WREN;
  // HCLK=168 MHz: address setup/hold 16 cycles each (~95 ns),
  // data 64 cycles (~381 ns), turnaround 16 cycles (~95 ns).
  FSMC_Bank1->BTCR[1] = 15U | (15U << 4) | (63U << 8) | (15U << 16);
  FSMC_Bank1->BTCR[0] |= FSMC_BCR1_MBKEN;
  __DSB();
}

// AD sees CPU address >> 1 on a 16-bit FSMC bus. AD=0xE -> byte offset 0x1C.
static volatile uint16_t *const scratch =
    reinterpret_cast<volatile uint16_t *>(0x6000001cUL);
static uint32_t passes = 0, failures = 0;

static bool check_word(uint16_t expected) {
  *scratch = expected;
  __DSB();
  // Two reads check retention as well as the immediate readback.
  const uint16_t actual = *scratch;
  __DSB();
  const uint16_t retained = *scratch;
  if (actual == expected && retained == expected) return true;
  Serial.print("FAIL expected=0x"); Serial.print(expected, HEX);
  Serial.print(" read=0x"); Serial.print(actual, HEX);
  Serial.print(" retained=0x"); Serial.println(retained, HEX);
  return false;
}

static void test_pass() {
  bool ok = true;
  const uint16_t fixed[] = {0x0000, 0xffff, 0xaaaa, 0x5555, 0xa55a, 0x5aa5};
  for (uint16_t value : fixed) if (!check_word(value)) ok = false;
  for (unsigned bit = 0; bit < 16; ++bit) {
    const uint16_t value = uint16_t(1U << bit);
    if (!check_word(value)) ok = false;
    if (!check_word(uint16_t(~value))) ok = false;
  }
  uint16_t state = 0xace1;
  for (unsigned i = 0; i < 256; ++i) {
    state = uint16_t((state >> 1) ^ ((state & 1U) ? 0xb400U : 0U));
    if (!check_word(state)) ok = false;
  }
  ++passes;
  if (!ok) ++failures;
  Serial.print(ok ? "PASS " : "FAILED "); Serial.print(passes);
  Serial.print(" (294 patterns, 588 reads), failed passes="); Serial.println(failures);
  digitalWrite(PA1, ok ? LOW : HIGH);  // On-board active-low LED.
}

void setup() {
  pinMode(PA1, OUTPUT);
  digitalWrite(PA1, HIGH);
  Serial.begin(115200);  // USB CDC; baud value does not set a UART clock.
  // Keep FSMC idle until the operator has loaded the FPGA test image.
}

void loop() {
  static bool enabled = false;
  static bool connected = false;
  static uint32_t last_test = 0;
  const uint32_t now = millis();
  const bool now_connected = bool(Serial);
  if (now_connected && !connected) {
    Serial.println("HP21xx FSMC test, STM32F407VE, HSE=8 MHz, HCLK=168 MHz");
    Serial.println("Load the matching FPGA image; send t to test, s to stop.");
    Serial.println("Scratch: CPU 0x6000001C / multiplexed AD address 0x000E");
  }
  connected = now_connected;
  while (Serial.available()) {
    const int command = Serial.read();
    if (command == 't' && !enabled) {
      fsmc_init();
      enabled = true;
      // Only starting from stopped schedules an immediate pass. Repeated t
      // characters (including keyboard auto-repeat) must not reset the timer.
      last_test = now - 1000U;
    } else if (command == 's') enabled = false;
  }
  if (!enabled) {
    // PA1 sinks current: 100 ms on every two seconds. Runs independently
    // of USB CDC/DTR, proving startup and the system clock without a host.
    digitalWrite(PA1, (now % 2000U < 100U) ? LOW : HIGH);
  } else if (now_connected && uint32_t(now - last_test) >= 1000U) {
    last_test = now;
    test_pass();  // During tests, LED shows the most recent pass/fail result.
  }
  delay(1);
}
