#include "backend.h"
#include <string.h>

namespace hp {
namespace {
bool expired(uint32_t now, uint32_t deadline) { return int32_t(now-deadline)>=0; }
}
void Backend::status(unsigned d, uint16_t bits, bool set) {
  bus_.write(set ? SetStatus : ClearStatus, uint16_t((d<<14)|bits));
}
void Backend::begin() {
  mode_=Idle;
  pending_=false;
  seek_completion_valid_=0;
  for (unsigned d=0; d<Drives; ++d) {
    drive_[d]=Drive{};
    seek_completion_command_[d]=0;
    failed_[d]=false;
    status(d, 0x1fff, false);
    status(d, images_.ready(d) ? FirstStatus : NotReady);
    log(ready_event(d,images_.ready(d)));
  }
  // CSR bits 8/9 only gate physical IRQ/DRQ outputs. Poll readable bits 7/6;
  // no dependency on the reserved/unwired interrupt pins.
  bus_.write(Csr, 0x0100);
}
void Backend::complete(bool attention_bit) {
  status(selected_, Busy, false);
  // Even an all-zero attention write completes commands in this FPGA protocol.
  bus_.write(Attention, attention_bit ? uint16_t(1U<<selected_) : 0);
  mark(Event::Complete);
  mode_=Idle;
}
void Backend::media_error(Event event) {
  error(event);
  failed_[selected_]=true;
  status(selected_, DataError|Unsafe|NotReady);
  complete();
}
void Backend::finish_write(bool check_overrun) {
  if (position_) {
    const unsigned bytes=((position_+SectorBytes-1)/SectorBytes)*SectorBytes;
    if (bytes!=position_) mark(Event::ZeroFill);
    memset(buffer_+position_, 0, bytes-position_);
    const bool written=images_.write(selected_, address_.offset(), buffer_, bytes);
    // A strobe can arrive while SD/FAT blocks. Capture any command packet
    // consumed by this CSR read, and reject late data before HP completion.
    const uint16_t csr=poll();
    if (check_overrun) discard_late(csr);
    if (!written) {
      media_error(Event::WriteError);
      return;
    }
  }
  complete(command_ != 9);
}
void Backend::discard_late(uint16_t csr) {
  if (!(csr&0x40)) return;
  (void)bus_.read(Data); // Acknowledge/discard; never append or stage a word.
  if (!overrun_reported_) {
    status(selected_,Overrun);
    mark(Event::TransferOverrun);
    overrun_reported_=true;
  }
}
void Backend::start_drain(bool writing) {
  mark(Event::Timeout);
  // Keep the command busy through the remainder of the physical data field.
  // This is sector geometry/rate, not a delay tuned to the late-word test.
  const unsigned words=position_/2%Words;
  const unsigned remaining=words ? Words-words : 0;
  deadline_+=(remaining*32+4)/5; // ceil(remaining * 6.4us), rollover-safe.
  mode_=writing ? WriteDrain : ReadDrain;
}
void Backend::drain(uint32_t now, uint16_t csr) {
  discard_late(csr);
  if (!expired(now,deadline_)) return;
  if (mode_==WriteDrain) finish_write();
  else complete();
}
void Backend::dispatch(uint16_t cmd, uint16_t seek, uint32_t now) {
  selected_=cmd&3;
  command_=cmd>>12;
  address_=Address::decode(seek);
  last_command_=cmd;
  last_rar_=seek;
  ++commands_;
  log(drive_event(selected_));
  switch (command_) {
    case 1: log(Event::Write); break;
    case 2: log(Event::Read); break;
    case 3: log(Event::Seek); break;
    case 5: log(Event::Refine); break;
    case 6: log(Event::Check); break;
    case 9: log(Event::Initialize); break;
    case 11: log(Event::Address); break;
    default: log(Event::Unknown); break;
  }
  if (command_==11) return; // ADDRESS RECORD is handled entirely in FPGA.
  if (command_!=1 && command_!=2 && command_!=3 && command_!=5 && command_!=6 && command_!=9) {
    // Match the reference daemon's default case: record the unexpected value,
    // but do not manufacture HP attention or command completion for it.
    error(Event::CommandError);
    return;
  }
  if (!images_.ready(selected_) || failed_[selected_]) {
    error(Event::OfflineError);
    status(selected_, NotReady);
    complete();
    return;
  }
  if (command_==3) { // SEEK RECORD: independent timed worker per drive.
    Drive &d=drive_[selected_];
    if (d.seeking) {
      // The earlier positioning operation continues (13210A manual 3-23).
      // Retain Busy and let that worker signal attention when it finishes;
      // an early completion would let HP issue another seek while still busy.
      error(Event::SeekBusyError);
      status(selected_, SeekCheck);
    } else if (!address_.valid()) {
      error(Event::SeekAddressError);
      status(selected_, SeekCheck);
      status(selected_, Busy|Seeking, false);
      bus_.write(Attention, uint16_t(1U<<selected_));
      mark(Event::Complete);
    } else {
      status(selected_, SeekCheck, false);
      status(selected_, Busy|Seeking);
      d.cylinder=address_.cylinder;
      d.seeking=true;
      d.deadline=now+SeekTimeUs;
    }
    return;
  }
  if (command_==5) { complete(false); return; } // REFINE SECTOR, as in model.
  if (!address_.valid()) {
    error(Event::AddressError);
    status(selected_, AddressError);
    complete();
    return;
  }
  if (drive_[selected_].cylinder!=address_.cylinder) {
    error(Event::CylinderError);
    status(selected_, AddressError);
    drive_[selected_].cylinder=0;
    // The reference read path still reads the addressed image after reporting
    // mismatch; write/initialize paths must not modify the wrong cylinder.
    if (command_!=2 && command_!=6) { complete(command_!=9); return; }
  }
  status(selected_, Busy);
  status(selected_, Flagged, false);
  position_=0;
  length_=address_.remaining();
  read_wait_=false;
  overrun_reported_=false;
  deadline_=now+WordTimeoutUs;
  if (command_==2) {
    if (!images_.read(selected_, address_.offset(), buffer_, length_)) {
      media_error(Event::ReadError); return;
    }
    mode_=ReadStart;
    deadline_=bus_.now_us(now)+transfer_start_us_;
  } else if (command_==6) {
    mode_=CheckCount;
  } else {
    // INITIALIZE DATA shares the write data path. Cylinder attribute metadata
    // and write-protect enforcement are intentionally deferred.
    mode_=WriteStart;
    deadline_=bus_.now_us(now)+transfer_start_us_;
  }
}
uint16_t Backend::poll() {
  // Every CSR read acknowledges command IRQ, even while transferring data.
  // Capture both command and RAR immediately so it cannot disappear unnoticed.
  const uint16_t csr=bus_.read(Csr);
  last_csr_=csr;
  if (csr&0x80) {
    request_csr_=csr;
    const uint16_t cmd=bus_.read(Command), seek=bus_.read(SeekRecord);
    if (pending_) {
      log(drive_event(cmd&3));
      ++errors_; last_error_=Event::PendingError;
      log(Event::PendingError); // The streaming backend has one software pending slot.
      status(cmd&3, Overrun);
    } else {
      pending_command_=cmd;
      pending_seek_=seek;
      pending_=true;
    }
  }
  return csr;
}
void Backend::step(uint32_t now) {
  const uint16_t csr=poll();
  now=bus_.now_us(now);
  for (unsigned d=0; d<Drives; ++d) {
    if (drive_[d].seeking && expired(now,drive_[d].deadline)) {
      drive_[d].seeking=false;
      // Match the reference worker: sample abort before clearing seek status.
      // Retain this exact read; USB reporting must not add bus transactions.
      const uint16_t completion_command=bus_.read(Command);
      seek_completion_command_[d]=completion_command;
      seek_completion_valid_|=uint8_t(1U<<d);
      status(d, Seeking|Busy|FirstStatus, false);
      // CLC may have aborted the seek's attention. Read the hardware latch at
      // completion, just as the simulation worker does.
      log(drive_event(d));
      if (!(completion_command&(1U<<(d+2)))) {
        bus_.write(Attention, uint16_t(1U<<d));
        log(Event::SeekComplete);
      } else log(Event::SeekAborted);
    }
  }
  if (mode_==Idle) {
    // HP POPIO also resets the FPGA's not-ready vector. There is no readable
    // reset counter/status register, so republish just media availability.
    // Never do these extra transactions in the word-transfer hot path.
    if (expired(now,refresh_)) {
      refresh_=now+10000U;
      for (unsigned d=0; d<Drives; ++d)
        status(d,NotReady,!images_.ready(d) || failed_[d]);
    }
    if (pending_) {
      const unsigned d=pending_command_&3, cmd=pending_command_>>12;
      // A read/write immediately after CLC of an in-flight seek waits for that
      // drive's worker; a new seek itself is processed to report SEEK CHECK.
      if (drive_[d].seeking && cmd!=3) return;
      pending_=false;
      dispatch(pending_command_,pending_seek_,now);
    }
    return;
  }
  if (mode_==ReadDrain || mode_==WriteDrain) {
    drain(now,csr);
    return;
  }
  if (mode_==ReadStart || mode_==WriteStart) {
    if (!expired(now,deadline_)) return;
    mode_=mode_==ReadStart ? Read : Write;
    deadline_+=WordTimeoutUs;
  }
  if (mode_==Write) {
    // CSR is a level latch, with no arrival timestamp. A pending word may
    // have arrived on time while this poll was delayed by an interrupt.
    // Only an expired EMPTY poll establishes the end of the valid prefix.
    if (csr&0x40) {
      if (position_) {
        const uint32_t elapsed=now-(deadline_-ResponseTimeoutUs);
        if (elapsed>longest_write_response_us_) longest_write_response_us_=elapsed;
      }
      const uint16_t word=bus_.read(Data);
      buffer_[position_++]=uint8_t(word);
      buffer_[position_++]=uint8_t(word>>8);
      deadline_=bus_.now_us(now)+ResponseTimeoutUs;
      if (position_==length_) { mark(Event::EndCylinder); status(selected_,EndCylinder); finish_write(false); }
    } else if (position_ && expired(now,deadline_)) {
      start_drain(true);
      drain(now,csr);
    } else if (expired(now,deadline_)) { mark(Event::Timeout); finish_write(); }
    return;
  }
  if (mode_==CheckCount) {
    if (csr&0x40) {
      // CHECK accepts one sector-count word, then proceeds without HP data
      // transfers (13210A manual 3-28/29). Waiting for further STC pulses
      // makes it time out before reaching the cylinder boundary.
      const unsigned sectors=bus_.read(Data)&63;
      if (sectors*SectorBytes>length_) {
        mark(Event::EndCylinder);
        status(selected_,EndCylinder);
      }
      // Exactly the remaining sectors succeeds; only a request beyond them
      // sets EOC. A zero-valued attention write still raises the command flag.
      complete(false);
    } else if (expired(now,deadline_)) {
      error(Event::CountTimeoutError); status(selected_,Overrun); complete(false);
    }
    return;
  }
  // READ DATA: stage a word, then await the HP's next STC.
  if (read_wait_) {
    if (!(csr&0x40)) {
      if (expired(now,deadline_)) {
        start_drain(false);
        drain(now,csr);
      }
      return;
    }
    const uint32_t elapsed=now-(deadline_-ResponseTimeoutUs);
    if (elapsed>longest_read_response_us_) longest_read_response_us_=elapsed;
    read_wait_=false;
    if (position_==length_) {
      mark(Event::EndCylinder); status(selected_,EndCylinder);
      complete();
      return;
    }
  }
  const uint16_t word=uint16_t(buffer_[position_]|(uint16_t(buffer_[position_+1])<<8));
  bus_.write(Data,word);
  position_+=2;
  read_wait_=true;
  deadline_=bus_.now_us(now)+ResponseTimeoutUs;
}
} // namespace hp
