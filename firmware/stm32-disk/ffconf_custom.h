#pragma once
// Use this pinned FatFs release's complete defaults, then select the options
// needed by the single-threaded backend. No formatter or exFAT support.
#define _USE_WRITE 1
#define _USE_IOCTL 1
// STM32SD's wrapper tests the legacy revision macro even for modern FatFs.
#define _FATFS 80286
#include "ffconf_default_80286.h"
#undef FF_FS_EXFAT
#define FF_FS_EXFAT 0
#undef FF_USE_LFN
#define FF_USE_LFN 2
#undef FF_MAX_LFN
#define FF_MAX_LFN 63
#undef FF_CODE_PAGE
#define FF_CODE_PAGE 437
#undef FF_FS_NORTC
#define FF_FS_NORTC 1
#undef FF_FS_LOCK
#define FF_FS_LOCK 5
