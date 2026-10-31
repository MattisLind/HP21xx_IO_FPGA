#include <Arduino.h>
#include <STM32SD.h>
#include "backend.h"
#include "media.h"
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

void fsmc_init();
static hp::Trace trace;

class FsmcBus : public hp::Bus {
 public:
  uint32_t now_us(uint32_t) override { return micros(); }
  uint16_t read(uint16_t reg) override {
    const uint16_t value=*reinterpret_cast<volatile uint16_t *>(0x60000000UL+2U*reg);
    __DSB();
    return value;
  }
  void write(uint16_t reg, uint16_t value) override {
    *reinterpret_cast<volatile uint16_t *>(0x60000000UL+2U*reg)=value;
    __DSB();
  }
};

class FatImages : public hp::Images, public hp::Media {
 public:
  hp::Config config;
  char message[128] = "SD not initialized";
  bool mount() override {
    SD.setDx(PC8, PC9, PC10, PC11);
    SD.setCK(PC12);
    SD.setCMD(PD2);
    if (!SD.begin()) {
      // A failed FAT mount can leave the disk driver registered; a failed HAL
      // init can leave the peripheral in ERROR. Reset both before retrying.
      unmount();
      trace.push(hp::Event::SdError);
      strcpy(message,"SD/FAT mount failed; retrying");
      return false;
    }
    trace.push(hp::Event::SdMounted);
    FIL file={};
    if (f_open(&file,"/hp13210.cfg",FA_READ)!=FR_OK) {
      trace.push(hp::Event::ConfigOpenError);
      strcpy(message,"Missing /hp13210.cfg; all drives offline"); return true;
    }
    char text[1025];
    UINT got=0;
    const auto config_size=f_size(&file);
    const bool size_ok=config_size<sizeof(text);
    const bool read_ok=size_ok && f_read(&file,text,sizeof(text)-1,&got)==FR_OK && got==config_size;
    const bool close_ok=f_close(&file)==FR_OK;
    if (!read_ok || !close_ok) { trace.push(hp::Event::ConfigReadError); strcpy(message,"Config unreadable or larger than 1024 bytes"); return true; }
    text[got]=0;
    if (memchr(text,0,got)) { trace.push(hp::Event::ConfigParseError); strcpy(message,"Config contains an embedded NUL"); return true; }
    if (!hp::parse_config(text,config,message,sizeof(message))) { trace.push(hp::Event::ConfigParseError); return true; }
    trace.push(hp::Event::ConfigLoaded);
    strcpy(message,"FAT mounted; unavailable/invalid images stay offline");
    for (unsigned d=0; d<hp::Drives; ++d) {
      if (!config.image[d][0]) continue;
      char path[80];
      snprintf(path,sizeof(path),"/images/%s",config.image[d]);
      // Open existing files only. Never append, truncate, create or format.
      if (f_open(&files_[d],path,FA_READ|FA_WRITE)!=FR_OK) {
        trace.push(hp::drive_event(d)); trace.push(hp::Event::ImageOpenError); continue;
      }
      if (f_size(&files_[d])!=hp::ImageBytes) {
        trace.push(hp::drive_event(d)); trace.push(hp::Event::ImageSizeError);
        f_close(&files_[d]); continue;
      }
      online_[d]=true;
    }
    return true;
  }
  void unmount() override {
    // Never f_close/f_sync old objects after card loss: those could write cached
    // data belonging to the old card onto a newly inserted card.
    memset(online_,0,sizeof(online_));
    memset(files_,0,sizeof(files_));
    config=hp::Config{};
    if (!SD.end()) (void)BSP_SD_DeInit();
    fault_=false;
    strcpy(message,"SD unavailable; waiting to reinitialize");
  }
  bool healthy() override { return BSP_SD_GetCardState()==MSD_OK; }
  bool faulted() const override { return fault_; }
  uint32_t now_ms(uint32_t) const override { return millis(); }
  void media_fault() {
    fault_=true;
    memset(online_,0,sizeof(online_));
  }
  bool ready(unsigned drive) const override { return online_[drive]; }
  bool read(unsigned d, uint32_t offset, uint8_t *data, unsigned size) override {
    if (!range(d,offset,size)) return false;
    UINT got=0;
    const bool ok=f_lseek(&files_[d],offset)==FR_OK &&
                  f_read(&files_[d],data,size,&got)==FR_OK && got==size;
    if (!ok) media_fault();
    return ok;
  }
  bool write(unsigned d, uint32_t offset, const uint8_t *data, unsigned size) override {
    if (!range(d,offset,size)) return false;
    UINT put=0;
    const bool ok=f_lseek(&files_[d],offset)==FR_OK &&
                  f_write(&files_[d],data,size,&put)==FR_OK && put==size &&
                  f_sync(&files_[d])==FR_OK;
    if (!ok) media_fault();
    return ok;
  }
 private:
  FIL files_[hp::Drives] = {};
  bool online_[hp::Drives] = {};
  bool fault_=false;
  bool range(unsigned d, uint32_t offset, unsigned size) const {
    return d<hp::Drives && online_[d] && offset<=hp::ImageBytes && size<=hp::ImageBytes-offset;
  }
};

static FsmcBus bus;
static FatImages images;
static hp::Backend backend(bus,images,&trace);
static hp::MediaRecovery media(images);

static char report_text[1024];
static unsigned report_length=0, report_position=0;
static void append_report(const char *format, ...) {
  const unsigned space=sizeof(report_text)-report_length;
  va_list args;
  va_start(args,format);
  const int n=vsnprintf(report_text+report_length,space,format,args);
  va_end(args);
  if (n>0) report_length+=unsigned(n)<space ? unsigned(n) : space-1;
}
static void report() {
  report_length=report_position=0;
  append_report("HP13210 SDIO/FAT disk backend; data=14 command=15 (octal)\r\n%s\r\n",images.message);
  append_report("SD mounted=%u attempts=%lu failures=%lu removals=%lu\r\n",
                unsigned(media.mounted()),static_cast<unsigned long>(media.attempts()),
                static_cast<unsigned long>(media.failures()),static_cast<unsigned long>(media.removals()));
  for (unsigned d=0; d<hp::Drives; ++d) {
    append_report("drive%u %s %s\r\n",d,images.ready(d) ? "READY /images/" : "OFFLINE",images.config.image[d]);
  }
  append_report("commands=%lu errors=%lu trace_dropped=%lu\r\nSend ? for status. Images are writable; write-protect is deferred.\r\n",
                static_cast<unsigned long>(backend.commands()),static_cast<unsigned long>(backend.errors()),
                static_cast<unsigned long>(trace.dropped()));
  append_report("FSMC csr=0x%04X request=0x%04X command=0x%04X rar=0x%04X last_error=%s\r\n",
                unsigned(backend.last_csr()),unsigned(backend.request_csr()),
                unsigned(backend.last_command()),unsigned(backend.last_rar()),backend.last_error());
  append_report("Seek completion valid=0x%X command[0..3]=%04X %04X %04X %04X\r\n",
                unsigned(backend.seek_completion_valid()),
                unsigned(backend.seek_completion_command(0)),unsigned(backend.seek_completion_command(1)),
                unsigned(backend.seek_completion_command(2)),unsigned(backend.seek_completion_command(3)));
  append_report("Experimental fixed seek delay=%lu us\r\n",
                static_cast<unsigned long>(hp::Backend::SeekTimeUs));
  append_report("Disk data start=%lu us; DMA response wait=%lu us; disk word period=6.4 us\r\n",
                static_cast<unsigned long>(hp::Backend::TransferStartUs),
                static_cast<unsigned long>(hp::Backend::ResponseTimeoutUs));
  append_report("Observed response maxima READ=%lu WRITE=%lu us (poll times, not HP edge timestamps)\r\n",
                static_cast<unsigned long>(backend.longest_read_response_us()),
                static_cast<unsigned long>(backend.longest_write_response_us()));
}

void setup() {
  pinMode(PA1,OUTPUT);
  digitalWrite(PA1,HIGH);
  Serial.begin(115200);
  trace.push(hp::Event::Boot);
  fsmc_init();
  backend.begin();
  media.begin(millis());
}

void loop() {
  // No delay(), USB printing, or filesystem calls in per-word protocol steps.
  backend.step(micros());
  const bool active=backend.active();
  // Only idle recovery may reinitialize FAT or republish all drive status.
  // begin() resets media quarantine/geometry but preserves diagnostic counters.
  auto media_change=hp::MediaRecovery::None;
  if (!active) {
    media_change=media.step(millis(),false);
    if (media_change!=hp::MediaRecovery::None) backend.begin();
  }
  static bool led_active=false;
  if (active) {
    if (!led_active) digitalWrite(PA1,LOW);
    led_active=true;
    return;
  }
  led_active=false;
  static bool connected=false, report_pending=false;
  // A partially sent trace line stays separate from multi-line status reports.
  static char trace_line[5];
  static unsigned trace_length=0, trace_position=0;
  const bool current=bool(Serial);
  if (current && (!connected || media_change!=hp::MediaRecovery::None)) report_pending=true;
  connected=current;
  if (Serial.available() && Serial.read()=='?') report_pending=true;
  if (current && report_pending && report_position==report_length && trace_position==trace_length) {
    report_pending=false;
    report();
  }
  if (current && report_position<report_length) {
    const int available=Serial.availableForWrite();
    unsigned count=report_length-report_position;
    if (count>32) count=32;
    if (available>0) {
      if (count>unsigned(available)) count=unsigned(available);
      report_position+=Serial.write(reinterpret_cast<const uint8_t *>(report_text+report_position),count);
    }
  } else if (current) {
    if (trace_position==trace_length) {
      hp::Event event;
      if (trace.pop(event)) {
        const char *code=hp::event_code(event);
        trace_length=strlen(code);
        memcpy(trace_line,code,trace_length);
        trace_line[trace_length++]='\r';
        trace_line[trace_length++]='\n';
        trace_position=0;
      }
    }
    const int available=Serial.availableForWrite();
    if (available>0 && trace_position<trace_length) {
      unsigned count=trace_length-trace_position;
      if (count>unsigned(available)) count=unsigned(available);
      trace_position+=Serial.write(reinterpret_cast<const uint8_t *>(trace_line+trace_position),count);
    }
  }
  digitalWrite(PA1,(millis()%2000U<100U) ? LOW : HIGH);
}
