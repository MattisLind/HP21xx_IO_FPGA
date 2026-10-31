#pragma once
#include <stdint.h>
#define MSD_OK 0
#define SD_DATATIMEOUT 1000U
typedef struct { uint32_t LogBlockNbr, LogBlockSize; } BSP_SD_CardInfo;
uint32_t HAL_GetTick(void);
uint8_t BSP_SD_Init(void);
uint8_t BSP_SD_GetCardState(void);
uint8_t BSP_SD_ReadBlocks(uint32_t *,uint32_t,uint32_t,uint32_t);
uint8_t BSP_SD_WriteBlocks(uint32_t *,uint32_t,uint32_t,uint32_t);
uint8_t BSP_SD_GetCardInfo(BSP_SD_CardInfo *);
