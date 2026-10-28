#pragma once
#include <stdint.h>

namespace hp {
enum class Event : uint8_t {
  Boot, SdMounted, ConfigLoaded,
  Drive0, Drive1, Drive2, Drive3,
  Ready0, Ready1, Ready2, Ready3,
  Offline0, Offline1, Offline2, Offline3,
  Write, Read, Seek, Refine, Check, Initialize, Address, Unknown,
  Complete, SeekComplete, SeekAborted, Timeout, ZeroFill, EndCylinder,
  OfflineError, SeekBusyError, SeekAddressError, CommandError, AddressError,
  CylinderError, ReadError, WriteError, PendingError, CountTimeoutError,
  SdError, ConfigOpenError, ConfigReadError, ConfigParseError,
  ImageOpenError, ImageSizeError, TransferOverrun, TraceOverflow
};

inline const char *event_code(Event event) {
  switch (event) {
    case Event::Boot: return "BT";
    case Event::SdMounted: return "SD";
    case Event::ConfigLoaded: return "CF";
    case Event::Drive0: return "D0";
    case Event::Drive1: return "D1";
    case Event::Drive2: return "D2";
    case Event::Drive3: return "D3";
    case Event::Ready0: return "R0";
    case Event::Ready1: return "R1";
    case Event::Ready2: return "R2";
    case Event::Ready3: return "R3";
    case Event::Offline0: return "N0";
    case Event::Offline1: return "N1";
    case Event::Offline2: return "N2";
    case Event::Offline3: return "N3";
    case Event::Write: return "WR";
    case Event::Read: return "RD";
    case Event::Seek: return "SK";
    case Event::Refine: return "RF";
    case Event::Check: return "CK";
    case Event::Initialize: return "IN";
    case Event::Address: return "AR";
    case Event::Unknown: return "??";
    case Event::Complete: return "CM";
    case Event::SeekComplete: return "SC";
    case Event::SeekAborted: return "SA";
    case Event::Timeout: return "TO";
    case Event::ZeroFill: return "ZF";
    case Event::EndCylinder: return "EC";
    case Event::TransferOverrun: return "OV";
    case Event::OfflineError: return "E01";
    case Event::SeekBusyError: return "E02";
    case Event::SeekAddressError: return "E03";
    case Event::CommandError: return "E04";
    case Event::AddressError: return "E05";
    case Event::CylinderError: return "E06";
    case Event::ReadError: return "E07";
    case Event::WriteError: return "E08";
    case Event::PendingError: return "E09";
    case Event::CountTimeoutError: return "E10";
    case Event::SdError: return "E11";
    case Event::ConfigOpenError: return "E12";
    case Event::ConfigReadError: return "E13";
    case Event::ConfigParseError: return "E14";
    case Event::ImageOpenError: return "E15";
    case Event::ImageSizeError: return "E16";
    case Event::TraceOverflow: return "E99";
  }
  return "??";
}

inline Event drive_event(unsigned drive) { return Event(unsigned(Event::Drive0)+drive); }
inline Event ready_event(unsigned drive, bool ready) {
  return Event(unsigned(ready ? Event::Ready0 : Event::Offline0)+drive);
}

// Single-threaded, fixed-size event queue. Enqueueing never calls USB or waits.
// Preserve old records, drop new ones on overflow, then emit one E99 on drain.
class Trace {
 public:
  static constexpr unsigned Capacity=1024;
  void push(Event event) {
    if (count_==Capacity) { ++dropped_; lost_=true; return; }
    events_[tail_]=event;
    tail_=(tail_+1)%Capacity;
    ++count_;
  }
  bool pop(Event &event) {
    if (count_) {
      event=events_[head_];
      head_=(head_+1)%Capacity;
      --count_;
      return true;
    }
    if (lost_) { lost_=false; event=Event::TraceOverflow; return true; }
    return false;
  }
  uint32_t dropped() const { return dropped_; }
 private:
  Event events_[Capacity] = {};
  unsigned head_=0, tail_=0, count_=0;
  uint32_t dropped_=0;
  bool lost_=false;
};
} // namespace hp
