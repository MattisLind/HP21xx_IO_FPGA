#include "drivers/sd_diskio.h"
#include "bsp_sd.h"
#include <assert.h>
#include <stdio.h>
static uint32_t ticks, probes, busy;
static int transfer_error;
uint32_t HAL_GetTick(void) { return ticks++; }
uint8_t BSP_SD_Init(void) { return MSD_OK; }
uint8_t BSP_SD_GetCardState(void) { ++probes; return probes<=busy; }
uint8_t BSP_SD_ReadBlocks(uint32_t *p,uint32_t sector,uint32_t count,uint32_t timeout) {
  (void)p; assert(sector==7 && count==1 && timeout==1000); return transfer_error;
}
uint8_t BSP_SD_WriteBlocks(uint32_t *p,uint32_t sector,uint32_t count,uint32_t timeout) {
  return BSP_SD_ReadBlocks(p,sector,count,timeout);
}
uint8_t BSP_SD_GetCardInfo(BSP_SD_CardInfo *p) { p->LogBlockNbr=1024; p->LogBlockSize=512; return MSD_OK; }
static void reset(uint32_t start,uint32_t busy_count) { ticks=start; probes=0; busy=busy_count; transfer_error=0; }
int main(void) {
  uint32_t data[128]={0};
  reset(0,0); assert(SD_Driver.disk_initialize(0)==0);
  reset(0,3); assert(SD_Driver.disk_read(0,(BYTE *)data,7,1)==RES_OK && probes==4);
  reset(0,3); assert(SD_Driver.disk_write(0,(BYTE *)data,7,1)==RES_OK && probes==4);
  reset(0,0); transfer_error=1;
  assert(SD_Driver.disk_read(0,(BYTE *)data,7,1)==RES_ERROR && !probes);
  // Removal after a successful block command used to hang forever here.
  reset(0,UINT32_MAX); assert(SD_Driver.disk_read(0,(BYTE *)data,7,1)==RES_ERROR && probes<=1001);
  reset(UINT32_MAX-500,UINT32_MAX);
  assert(SD_Driver.disk_write(0,(BYTE *)data,7,1)==RES_ERROR && probes<=1001);
  reset(0,UINT32_MAX); assert(SD_Driver.disk_ioctl(0,CTRL_SYNC,0)==RES_ERROR);
  reset(0,4); assert(SD_Driver.disk_ioctl(0,CTRL_SYNC,0)==RES_OK && probes==5);
  puts("PASS: real SD driver busy completion, removal timeout, timer wrap and CTRL_SYNC");
}
