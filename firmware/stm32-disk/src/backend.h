#pragma once
#include <stddef.h>
#include <stdint.h>
#include "trace.h"

namespace hp {
constexpr unsigned Drives = 4, Cylinders = 203, Heads = 4, Sectors = 24;
constexpr unsigned Words = 128, SectorBytes = Words * 2;
constexpr uint32_t ImageBytes = Cylinders * Heads * Sectors * SectorBytes;
constexpr unsigned BufferBytes = 2 * Sectors * SectorBytes;
enum Register : uint16_t { Csr=0, Command=2, Data=4, Attention=6,
                          SetStatus=8, ClearStatus=10, SeekRecord=12 };
enum Status : uint16_t { DataError=1, Busy=2, Flagged=4, AddressError=8,
  EndCylinder=16, NotReady=32, SeekCheck=64, DataProtect=128, Unsafe=256,
  Overrun=512, FirstStatus=1024, Seeking=2048, SeekAborted=4096 };

struct Config {
  // Filenames only, relative to /images. Empty means offline.
  char image[Drives][64] = {};
};
bool parse_config(const char *text, Config &config, char *error, size_t size);

struct Address {
  unsigned cylinder=0, head=0, sector=0;
  bool valid() const { return cylinder<Cylinders && head<Heads && sector<Sectors; }
  uint32_t offset() const {
    return ((cylinder * Heads + head) * Sectors + sector) * SectorBytes;
  }
  unsigned remaining() const { return ((2 - (head & 1)) * Sectors - sector) * SectorBytes; }
  static Address decode(uint16_t v) { return {unsigned(v>>7)&255, unsigned(v>>5)&3, unsigned(v)&31}; }
};

struct Bus {
  virtual uint16_t read(uint16_t reg)=0;
  virtual void write(uint16_t reg, uint16_t value)=0;
  virtual ~Bus() = default;
};
struct Images {
  virtual bool ready(unsigned drive) const=0;
  virtual bool read(unsigned drive, uint32_t offset, uint8_t *data, unsigned size)=0;
  virtual bool write(unsigned drive, uint32_t offset, const uint8_t *data, unsigned size)=0;
  virtual ~Images() = default;
};

// Polling replacement for tb_hp2116.sv's daemon and asynchronous seek workers.
// One step per main-loop iteration; no allocation, USB output, or delay calls.
class Backend {
 public:
  Backend(Bus &bus, Images &images, Trace *trace=nullptr): bus_(bus), images_(images), trace_(trace) {}
  void begin();
  void step(uint32_t now_us);
  bool active() const {
    if (mode_ != Idle || pending_) return true;
    for (const auto &d: drive_) if (d.seeking) return true;
    return false;
  }
  uint32_t commands() const { return commands_; }
  uint32_t errors() const { return errors_; }
  uint16_t last_csr() const { return last_csr_; }
  uint16_t request_csr() const { return request_csr_; }
  uint16_t last_command() const { return last_command_; }
  uint16_t last_rar() const { return last_rar_; }
  uint16_t seek_completion_command(unsigned drive) const { return seek_completion_command_[drive]; }
  uint8_t seek_completion_valid() const { return seek_completion_valid_; }
  const char *last_error() const { return errors_ ? event_code(last_error_) : "none"; }
  // Initial bring-up thresholds in real microseconds, not simulator nanoseconds.
  // Experimental fixed delay; not a measured mechanical drive timing model.
  static constexpr uint32_t WordTimeoutUs=100, SeekTimeUs=500;
 private:
  enum Mode { Idle, Read, Write, CheckCount, Check } mode_=Idle;
  struct Drive { unsigned cylinder=0; bool seeking=false; uint32_t deadline=0; } drive_[Drives];
  Bus &bus_;
  Images &images_;
  Trace *trace_;
  alignas(4) uint8_t buffer_[BufferBytes] = {};
  uint16_t pending_command_=0, pending_seek_=0;
  uint16_t last_csr_=0, request_csr_=0, last_command_=0, last_rar_=0;
  uint16_t seek_completion_command_[Drives] = {};
  uint8_t seek_completion_valid_=0;
  Event last_error_=Event::Boot;
  bool pending_=false, read_wait_=false;
  bool failed_[Drives] = {};
  unsigned selected_=0, command_=0, position_=0, length_=0, check_words_=0;
  Address address_;
  uint32_t deadline_=0, refresh_=0, commands_=0, errors_=0;
  void status(unsigned drive, uint16_t bits, bool set=true);
  void complete(bool attention_bit=true);
  void finish_write();
  void log(Event event) { if (trace_) trace_->push(event); }
  void mark(Event event) { log(drive_event(selected_)); log(event); }
  void error(Event event) { ++errors_; last_error_=event; mark(event); }
  void media_error(Event event);
  void dispatch(uint16_t command, uint16_t seek, uint32_t now);
};
} // namespace hp
