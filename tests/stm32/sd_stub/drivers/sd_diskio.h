#pragma once
#include <stdint.h>
typedef uint8_t BYTE, DSTATUS;
typedef uint32_t LBA_t, DWORD;
typedef uint16_t WORD;
typedef unsigned UINT;
typedef enum { RES_OK, RES_ERROR, RES_WRPRT, RES_NOTRDY, RES_PARERR } DRESULT;
#define STA_NOINIT 1
#define CTRL_SYNC 0
#define GET_SECTOR_COUNT 1
#define GET_SECTOR_SIZE 2
#define GET_BLOCK_SIZE 3
typedef struct {
  DSTATUS (*disk_initialize)(BYTE);
  DSTATUS (*disk_status)(BYTE);
  DRESULT (*disk_read)(BYTE,BYTE *,LBA_t,UINT);
  DRESULT (*disk_write)(BYTE,const BYTE *,LBA_t,UINT);
  DRESULT (*disk_ioctl)(BYTE,BYTE,void *);
} Diskio_drvTypeDef;
extern const Diskio_drvTypeDef SD_Driver;
