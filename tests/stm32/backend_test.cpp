#include "backend.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <string>
#include <functional>

struct Bus : hp::Bus {
  uint16_t csr=0, cmd=0, rar=0, word=0, attention=0, status[4]={};
  std::vector<uint16_t> output, attention_writes;
  unsigned consumed=0;
  std::vector<unsigned> accesses;
  uint16_t read(uint16_t reg) override {
    accesses.push_back(reg);
    switch (reg) {
      case hp::Csr: { auto v=csr; csr&=~0x80; return v; }
      case hp::Command: return cmd;
      case hp::SeekRecord: return rar;
      case hp::Data: csr&=~0x40; ++consumed; return word;
      default: assert(false); return 0;
    }
  }
  void write(uint16_t reg, uint16_t value) override {
    accesses.push_back(0x10000U|reg);
    if (reg==hp::SetStatus) status[value>>14]|=value&0x1fff;
    else if (reg==hp::ClearStatus) status[value>>14]&=~(value&0x1fff);
    else if (reg==hp::Attention) { attention|=value; attention_writes.push_back(value); }
    else if (reg==hp::Data) { output.push_back(value); csr&=~0x40; }
    else assert(reg==hp::Csr);
  }
  void command(unsigned command, unsigned drive, hp::Address address) {
    assert(!(csr&0x80));
    cmd=uint16_t((command<<12)|drive);
    rar=uint16_t((address.cylinder<<7)|(address.head<<5)|address.sector);
    csr|=0x80;
  }
  void input(uint16_t value) { word=value; csr|=0x40; }
};
struct Images : hp::Images {
  bool online[4]={true,true,false,false}, fail_read=false, fail_write=false;
  std::vector<uint8_t> bytes[2] = {std::vector<uint8_t>(hp::ImageBytes,0x5a),
                                  std::vector<uint8_t>(hp::ImageBytes,0xa5)};
  unsigned reads=0, writes=0, written=0;
  std::function<void()> during_write;
  bool ready(unsigned d) const override { return online[d]; }
  bool read(unsigned d,uint32_t off,uint8_t *p,unsigned size) override {
    assert(d<2 && off+size<=hp::ImageBytes);
    ++reads;
    if (fail_read) return false;
    memcpy(p,bytes[d].data()+off,size); return true;
  }
  bool write(unsigned d,uint32_t off,const uint8_t *p,unsigned size) override {
    assert(d<2 && off+size<=hp::ImageBytes);
    ++writes; written=size;
    if (during_write) during_write();
    if (fail_write) return false;
    memcpy(bytes[d].data()+off,p,size); return true;
  }
};
struct Fixture { Bus bus; Images images; hp::Trace trace; hp::Backend engine{bus,images,&trace}; Fixture(){ engine.begin(); } };

static std::vector<std::string> take_trace(hp::Trace &trace) {
  std::vector<std::string> codes;
  hp::Event event;
  while (trace.pop(event)) codes.emplace_back(hp::event_code(event));
  return codes;
}
static bool contains(const std::vector<std::string> &codes, const char *code) {
  for (const auto &c:codes) if (c==code) return true;
  return false;
}

static void config_tests() {
  hp::Config c;
  char error[128];
  assert(hp::parse_config("# test\r\ndrive0 = rte.img\r\ndrive3=diag.img\ndrive2=none\ndrive1=\n",c,error,sizeof(error)));
  assert(!strcmp(c.image[0],"rte.img") && !strcmp(c.image[3],"diag.img") && !c.image[2][0]);
  const char *bad[]={"drive4=x", "drive0=../x", "drive0=/images/x", "drive0=x\ndrive0=y",
    "drive0=x\ndrive3=X", "drive3=x\ndrive1=x", "drive0=a/b", "writeprotect=true"};
  for (auto text:bad) { assert(!hp::parse_config(text,c,error,sizeof(error))); assert(error[0]); }
}
static void startup_seek_tests() {
  Fixture f;
  assert(f.bus.status[0]==hp::FirstStatus && f.bus.status[2]==hp::NotReady);
  f.bus.command(3,1,{202,3,23}); f.engine.step(0);
  assert(f.bus.status[1]&(hp::Busy|hp::Seeking));
  f.engine.step(hp::Backend::SeekTimeUs-1); assert(!f.bus.attention);
  f.bus.accesses.clear();
  f.engine.step(hp::Backend::SeekTimeUs); assert(f.bus.attention==2);
  assert((f.bus.accesses==std::vector<unsigned>{hp::Csr, hp::Command,
          0x10000U|hp::ClearStatus, 0x10000U|hp::Attention}));
  assert(f.engine.seek_completion_valid()==2);
  assert(f.engine.seek_completion_command(1)==0x3001);
  assert(!(f.bus.status[1]&(hp::Busy|hp::Seeking|hp::FirstStatus)));
  // Invalid RAR does not address memory outside the image.
  f.bus.command(3,0,{203,0,0}); f.engine.step(5000);
  assert(f.bus.status[0]&hp::SeekCheck);
  f.bus.command(3,0,{0,0,0}); f.engine.step(6000);
  f.bus.cmd|=1<<2; // CLC/abort latch for drive zero.
  f.bus.attention=0; f.engine.step(10000); assert(!f.bus.attention);
  assert(f.engine.seek_completion_valid()==3);
  assert(f.engine.seek_completion_command(0)==0x3004);
  assert(f.engine.seek_completion_command(1)==0x3001);
}

static void seek_geometry_tests() {
  Fixture f;
  for (unsigned d=0; d<4; ++d) f.images.online[d]=true;
  f.engine.begin();
  uint32_t now=0;
  // Seek must not access sector storage. Exercise each drive and every head,
  // at both cylinder/sector boundaries, then reject each invalid field.
  for (unsigned d=0; d<4; ++d) {
    for (unsigned h=0; h<4; ++h) {
      for (auto cylinder : {0U, 202U}) for (auto sector : {0U, 23U}) {
        f.bus.attention=0;
        f.bus.command(3,d,{cylinder,h,sector}); f.engine.step(now);
        assert(f.bus.attention==0 && (f.bus.status[d]&hp::Busy));
        f.engine.step(now+hp::Backend::SeekTimeUs-1);
        assert(f.bus.attention==0);
        f.engine.step(now+hp::Backend::SeekTimeUs);
        assert(f.bus.attention==(1U<<d));
        assert(!(f.bus.status[d]&(hp::Busy|hp::Seeking|hp::SeekCheck)));
        now+=hp::Backend::SeekTimeUs+10;
      }
    }
    for (auto address : {hp::Address{203,0,0}, hp::Address{255,0,0},
                         hp::Address{0,0,24}, hp::Address{0,0,31}}) {
      f.bus.attention=0;
      f.bus.command(3,d,address); f.engine.step(now);
      assert(f.bus.status[d]&hp::SeekCheck);
      assert(!(f.bus.status[d]&hp::Busy));
      assert(f.bus.attention==(1U<<d));
      now+=hp::Backend::SeekTimeUs+10;
    }
  }
  assert(f.images.reads==0 && f.images.writes==0);
}

static void seek_busy_recovery_tests() {
  Fixture f;
  f.bus.command(3,0,{1,0,0}); f.engine.step(0);
  f.bus.command(3,0,{8,0,0}); f.engine.step(10);
  assert(f.bus.status[0]&hp::SeekCheck);
  assert(f.bus.status[0]&hp::Busy);
  assert(f.bus.attention==0);
  f.engine.step(hp::Backend::SeekTimeUs-1); assert(f.bus.attention==0);
  // STATUS can replace the live command while positioning continues.
  f.bus.cmd=0;
  f.engine.step(hp::Backend::SeekTimeUs);
  assert(f.bus.attention==1 && !(f.bus.status[0]&(hp::Busy|hp::Seeking)));
  assert(f.bus.status[0]&hp::SeekCheck);
  // The next valid seek must recover without another false SEEK BUSY error.
  f.bus.attention=0;
  f.bus.command(3,0,{7,3,23}); f.engine.step(hp::Backend::SeekTimeUs+10);
  assert(!(f.bus.status[0]&hp::SeekCheck));
  assert(f.bus.status[0]&hp::Busy);
  f.engine.step(2*hp::Backend::SeekTimeUs+10);
  assert(f.bus.attention==1 && f.engine.errors()==1);
  assert(f.images.reads==0 && f.images.writes==0);
}
static void read_tests() {
  Fixture f;
  f.images.bytes[0][0]=0x34; f.images.bytes[0][1]=0x12;
  f.bus.command(2,0,{0,0,0}); f.engine.step(0);
  assert(f.images.reads==1);
  f.engine.step(1); assert(f.bus.output.back()==0x1234);
  // No further filesystem calls in the word handshake.
  for (unsigned i=0;i<127;++i) { f.bus.csr|=0x40; f.engine.step(i+2); }
  assert(f.bus.output.size()==128 && f.images.reads==1);
  f.engine.step(1000); assert(!f.engine.active() && f.bus.attention==1);
  assert(f.images.writes==0);
}
static void write_tests() {
  Fixture f;
  f.bus.command(1,0,{0,0,0}); f.engine.step(0);
  f.bus.input(0x1234); f.engine.step(1);
  f.bus.input(0xabcd); f.engine.step(2);
  f.engine.step(1000);
  assert(!f.engine.active() && f.images.written==256);
  assert(f.images.bytes[0][0]==0x34 && f.images.bytes[0][1]==0x12);
  assert(f.images.bytes[0][2]==0xcd && f.images.bytes[0][3]==0xab);
  for (unsigned i=4;i<256;++i) assert(f.images.bytes[0][i]==0);
  assert(f.images.bytes[0][256]==0x5a); // Following sectors unchanged.
  // Completed sectors plus a partial one are persisted, without truncating.
  f.bus.command(1,0,{0,0,1}); f.engine.step(2000);
  for (unsigned i=0;i<129;++i) { f.bus.input(uint16_t(i)); f.engine.step(2001+i); }
  f.engine.step(3000); assert(f.images.written==512);
  assert(f.images.bytes[0][256]==0 && f.images.bytes[0][258]==1);
  assert(f.images.bytes[0][768]==0x5a);
}
static void late_word_tests() {
  // Actual S1 step32 pattern: two valid words, then a third after about50us.
  // Poll in between, as the running backend does. The third must be discarded
  // while the sector is still being padded, not appended to the image.
  for (uint32_t start : {0U,0xfffffff0U}) {
    Fixture f;
    const hp::Address address{0,1,7};
    f.bus.command(1,0,address); f.engine.step(start);
    f.bus.input(0x1234); f.engine.step(start+1);
    f.bus.input(0x5678); f.engine.step(start+2);
    for (unsigned i=3;i<52;++i) f.engine.step(start+i);
    assert(f.engine.active() && f.bus.attention==0);
    f.bus.input(0xbeef); f.engine.step(start+52);
    assert(f.bus.status[0]&hp::Overrun);
    assert(f.engine.active() && f.bus.attention==0 && f.images.writes==0);
    f.engine.step(start+2000);
    assert(!f.engine.active() && f.bus.attention==1 && f.images.written==256);
    const unsigned off=address.offset();
    assert(f.images.bytes[0][off]==0x34 && f.images.bytes[0][off+2]==0x78);
    for (unsigned i=4;i<256;++i) assert(f.images.bytes[0][off+i]==0);
    assert(f.images.bytes[0][off+256]==0x5a);
  }
  // Slow synchronous SD/FAT writes must not hide a late strobe or consume a
  // queued command without retaining its command/RAR snapshot.
  Fixture io;
  io.images.during_write=[&] {
    io.bus.input(0xbeef);
    io.bus.command(3,1,{7,0,0});
  };
  io.bus.command(1,0,{0,0,0}); io.engine.step(0);
  io.bus.input(0x1234); io.engine.step(1);
  io.engine.step(2000);
  assert(io.bus.status[0]&hp::Overrun);
  assert(io.images.bytes[0][2]==0 && io.bus.consumed==2);
  io.engine.step(2001); io.engine.step(6001);
  assert(io.bus.attention==3);
  // The corresponding step35 READ overrun must not stage another HP word.
  Fixture read;
  read.bus.command(2,0,{0,1,7}); read.engine.step(0); read.engine.step(1);
  for (unsigned i=0;i<30;++i) { read.bus.csr|=0x40; read.engine.step(2+i); }
  for (unsigned i=32;i<82;++i) read.engine.step(i);
  assert(read.engine.active() && read.bus.attention==0);
  const unsigned staged=read.bus.output.size();
  read.bus.input(0xbeef); read.engine.step(82);
  assert(read.bus.status[0]&hp::Overrun);
  read.engine.step(2000);
  assert(!read.engine.active() && read.bus.attention==1);
  assert(read.bus.output.size()==staged && read.images.writes==0);
}
static void response_boundary_tests() {
  // A first-word setup wait is not the interword deadline. Five-us gaps
  // remain valid; a word at the rounded six-us deadline is already late.
  for (unsigned command : {1U,9U}) {
    Fixture f;
    f.bus.command(command,0,{0,0,0}); f.engine.step(0);
    f.bus.input(0x1234); f.engine.step(50);
    f.bus.input(0x5678); f.engine.step(55);
    f.bus.input(0xbeef); f.engine.step(61);
    assert(f.bus.status[0]&hp::Overrun);
    assert(f.engine.active() && f.bus.attention_writes.empty());
    f.engine.step(2000);
    assert(f.images.bytes[0][2]==0x78 && f.images.bytes[0][4]==0);
    assert(f.bus.attention_writes==std::vector<uint16_t>{uint16_t(command==1 ? 1 : 0)});
  }
  for (unsigned words : {1U,2U,30U,127U,128U,129U}) {
    Fixture f;
    f.bus.command(1,0,{0,0,0}); f.engine.step(0);
    uint32_t now=50;
    for (unsigned i=0;i<words;++i,now+=5) {
      f.bus.input(uint16_t(0x1000+i)); f.engine.step(now);
    }
    const uint32_t last=now-5;
    f.engine.step(last+5);
    assert(f.engine.active() && f.bus.attention==0);
    f.engine.step(last+6);
    if (words%128) assert(f.engine.active() && f.bus.attention==0);
    f.engine.step(last+1000);
    assert(!f.engine.active() && !(f.bus.status[0]&hp::Overrun));
    assert(f.bus.consumed==words && f.bus.attention==1);
    for (unsigned i=0;i<words;++i) {
      assert(f.images.bytes[0][2*i]==uint8_t(i));
      assert(f.images.bytes[0][2*i+1]==0x10);
    }
    for (unsigned i=2*words;i<f.images.written;++i) assert(f.images.bytes[0][i]==0);
    assert(f.images.bytes[0][f.images.written]==0x5a);
    // Once completion is signalled, a new preloaded data word is not an
    // overrun belonging to the already completed operation.
    f.bus.input(0xbeef); f.engine.step(last+1010);
    assert(!(f.bus.status[0]&hp::Overrun) && f.bus.consumed==words);
  }
  Fixture read;
  read.bus.command(2,0,{0,0,0}); read.engine.step(0); read.engine.step(50);
  for (unsigned i=1;i<=30;++i) { read.bus.csr|=0x40; read.engine.step(50+5*i); }
  read.engine.step(2000);
  assert(!read.engine.active() && !(read.bus.status[0]&hp::Overrun));
  assert(read.bus.output.size()==31 && read.bus.attention==1);
}
static void end_cylinder_and_errors() {
  Fixture f;
  // The very last sector of the image. No extra word wraps past the image end.
  f.bus.command(3,0,{202,3,23}); f.engine.step(0); f.engine.step(4000);
  f.bus.command(1,0,{202,3,23}); f.engine.step(4001);
  for (unsigned i=0;i<128;++i) { f.bus.input(0xfeed); f.engine.step(4002+i); }
  assert(!f.engine.active() && f.images.written==256);
  assert(f.bus.status[0]&hp::EndCylinder);
  assert(f.images.bytes[0].back()==0xfe);
  // I/O failure is surfaced as drive errors, never a fabricated successful write.
  f.images.fail_write=true;
  f.bus.command(1,0,{202,3,23}); f.engine.step(5000);
  f.bus.input(0xbeef); f.engine.step(5001); f.engine.step(6000);
  assert(f.bus.status[0]&(hp::DataError|hp::Unsafe|hp::NotReady));
  assert(f.engine.errors()==1);
  Fixture offline;
  offline.bus.command(2,3,{0,0,0}); offline.engine.step(0);
  assert(offline.bus.status[3]&hp::NotReady);
  assert(!offline.images.reads);
}
static void pending_and_check_tests() {
  Fixture f;
  f.bus.command(3,0,{1,0,0}); f.engine.step(0);
  // Match the model: a following read waits for its seek worker.
  f.bus.command(2,0,{1,0,0}); f.engine.step(1);
  assert(!f.images.reads);
  f.engine.step(4000); assert(f.images.reads==1);
  f.engine.step(4001); f.engine.step(5000); assert(!f.engine.active());
  // A command during a stream is captured despite CSR's destructive read.
  Fixture q;
  q.bus.command(2,0,{0,0,0}); q.engine.step(0); q.engine.step(1);
  q.bus.command(3,1,{7,0,0}); q.engine.step(2);
  q.engine.step(1000); q.engine.step(1001); q.engine.step(1501);
  assert(q.bus.attention&2);
}
static void check_data_tests() {
  Fixture f;
  for (unsigned d=0; d<4; ++d) f.images.online[d]=true;
  auto check = [&](unsigned drive, hp::Address address, uint16_t count, bool eoc) {
    f.engine.begin();
    f.bus.attention=8; // Completion must not manufacture a drive attention bit.
    f.bus.attention_writes.clear();
    f.bus.output.clear();
    f.bus.consumed=0;
    take_trace(f.trace);
    f.bus.command(6,drive,address); f.engine.step(0);
    assert(f.engine.active() && (f.bus.status[drive]&hp::Busy));
    f.bus.input(count); f.engine.step(1);
    // No more HP words or STC pulses. Even slow polling must not turn CHECK
    // into a read timeout; it is an autonomous operation (manual 3-28/29).
    for (unsigned i=0; i<4 && f.engine.active(); ++i)
      f.engine.step(1000+i*1000);
    assert(bool(f.bus.status[drive]&hp::EndCylinder)==eoc);
    assert(!f.engine.active() && !(f.bus.status[drive]&hp::Busy));
    assert(f.bus.consumed==1 && f.bus.output.empty());
    assert(f.bus.attention==8 && f.bus.attention_writes==std::vector<uint16_t>{0});
    const auto trace=take_trace(f.trace);
    assert(!contains(trace,"TO") && contains(trace,"CM"));
    assert(contains(trace,"EC")==eoc && f.engine.errors()==0);
    assert(f.images.reads==0 && f.images.writes==0);
  };
  // DSN151302 S1 step30: exactly 48 sectors fits; 49 attempts to cross EOC.
  check(0,{0,0,0},49,true);
  for (unsigned n : {1U,2U,4U,8U,16U,32U,48U}) check(0,{0,0,0},n,false);
  // Both two-head cylinder boundaries, on every drive, including nonzero
  // starting sectors and the very last sector of each track.
  for (unsigned d=0; d<4; ++d) for (unsigned h=0; h<4; ++h)
    for (unsigned sector : {0U,7U,23U}) {
      const unsigned available=(h%2 ? 24U : 48U)-sector;
      check(d,{0,h,sector},available,false);
      check(d,{0,h,sector},available+1,true);
    }
  check(0,{0,0,0},0,false); // Preserve the model's zero-count no-op.
  check(0,{0,0,0},0xffc1,false); // Only the six count bits are significant.
}
static void reset_and_boundary_tests() {
  Fixture f;
  // POPIO resets readiness in the FPGA without resetting this processor.
  f.bus.status[0]=hp::NotReady;
  f.engine.step(0);
  assert(!(f.bus.status[0]&hp::NotReady) && (f.bus.status[3]&hp::NotReady));
  // No host words: no image changes on an empty timed-out write.
  f.bus.command(1,0,{0,0,0}); f.engine.step(1); f.engine.step(102);
  assert(!f.images.writes && !f.engine.active());
  // Independent seeks on both drives, including timer rollover.
  Fixture s;
  s.bus.command(3,0,{1,0,0}); s.engine.step(0xfffffff0U);
  s.bus.command(3,1,{2,0,0}); s.engine.step(0xfffffff1U);
  s.engine.step(hp::Backend::SeekTimeUs-17); assert(!s.bus.attention);
  s.engine.step(hp::Backend::SeekTimeUs-15); assert(s.bus.attention==3);
  for (unsigned h=0;h<4;++h) {
    hp::Address a{0,h,23};
    assert(a.remaining()==(h%2 ? 256U : 25U*256));
  }
  // Reading the last sector must finish without accessing outside the image.
  Fixture r;
  r.bus.command(3,0,{202,3,23}); r.engine.step(0); r.engine.step(4000);
  r.bus.command(2,0,{202,3,23}); r.engine.step(4001); r.engine.step(4002);
  for (unsigned i=0;i<128;++i) { r.bus.csr|=0x40; r.engine.step(4003+i); }
  assert(!r.engine.active() && r.bus.output.size()==128 && (r.bus.status[0]&hp::EndCylinder));
  // Failed media stays quarantined during periodic availability refresh.
  Fixture bad;
  bad.images.fail_read=true;
  bad.bus.command(2,0,{0,0,0}); bad.engine.step(0); bad.engine.step(20000);
  assert(bad.bus.status[0]&hp::NotReady);
  bad.images.fail_read=false;
  bad.bus.command(2,0,{0,0,0}); bad.engine.step(20001);
  assert(bad.images.reads==1); // No automatic retry after a media error.
}
static void trace_tests() {
  for (unsigned i=0; i<=unsigned(hp::Event::TraceOverflow); ++i) {
    const char *code=hp::event_code(hp::Event(i));
    assert(strlen(code)>=2 && strlen(code)<=3);
  }
  hp::Trace queue;
  for (unsigned i=0;i<hp::Trace::Capacity;++i) queue.push(i%2 ? hp::Event::Write : hp::Event::Read);
  for (unsigned i=0;i<7;++i) queue.push(hp::Event::Seek);
  assert(queue.dropped()==7);
  hp::Event event;
  for (unsigned i=0;i<hp::Trace::Capacity;++i) {
    assert(queue.pop(event));
    assert(event==(i%2 ? hp::Event::Write : hp::Event::Read));
  }
  assert(queue.pop(event) && event==hp::Event::TraceOverflow);
  assert(!queue.pop(event));
  // Ring wraparound preserves records, and the overflow marker is one-shot.
  queue.push(hp::Event::Seek); assert(queue.pop(event) && event==hp::Event::Seek);
  assert(!queue.pop(event));

  Fixture f;
  assert((take_trace(f.trace)==std::vector<std::string>{"R0","R1","N2","N3"}));
  f.bus.command(1,0,{0,0,0}); f.engine.step(0);
  f.bus.input(0xabcd); f.engine.step(1); f.engine.step(1000);
  assert((take_trace(f.trace)==std::vector<std::string>{"D0","WR","D0","TO","D0","ZF","D0","CM"}));
  assert(f.engine.errors()==0); // Normal short-transfer timeout is not an error.
  f.bus.command(2,3,{0,0,0}); f.engine.step(2000);
  assert(contains(take_trace(f.trace),"E01"));

  Fixture seek;
  seek.bus.command(3,0,{0,0,0}); seek.engine.step(0);
  seek.bus.command(3,0,{0,0,0}); seek.engine.step(1);
  assert(contains(take_trace(seek.trace),"E02"));
  seek.bus.cmd|=1<<2; seek.engine.step(4000);
  assert((take_trace(seek.trace)==std::vector<std::string>{"D0","SA"}));
  seek.bus.command(3,0,{203,0,0}); seek.engine.step(5000);
  assert(contains(take_trace(seek.trace),"E03"));
  seek.bus.command(7,0,{0,0,0}); seek.engine.step(5001);
  assert(contains(take_trace(seek.trace),"E04"));
  seek.bus.command(2,0,{203,0,0}); seek.engine.step(5002);
  assert(contains(take_trace(seek.trace),"E05"));
  seek.bus.command(1,0,{1,0,0}); seek.engine.step(5003);
  assert(contains(take_trace(seek.trace),"E06"));

  Fixture media;
  media.images.fail_read=true;
  media.bus.command(2,0,{0,0,0}); media.engine.step(0);
  assert(contains(take_trace(media.trace),"E07"));
  media.images.fail_write=true;
  media.bus.command(1,1,{0,0,0}); media.engine.step(1);
  media.bus.input(123); media.engine.step(2); media.engine.step(1000);
  assert(contains(take_trace(media.trace),"E08"));

  Fixture pending;
  pending.bus.command(2,0,{0,0,0}); pending.engine.step(0); pending.engine.step(1);
  pending.bus.command(3,1,{0,0,0}); pending.engine.step(2);
  pending.bus.command(3,0,{0,0,0}); pending.engine.step(3);
  assert(contains(take_trace(pending.trace),"E09"));
  Fixture check;
  check.bus.command(6,0,{0,0,0}); check.engine.step(0); check.engine.step(101);
  assert(contains(take_trace(check.trace),"E10"));

  // Completion must restore drive context after an overlapping seek finishes.
  Fixture context;
  context.bus.command(3,1,{0,0,0}); context.engine.step(0);
  context.bus.command(2,0,{0,0,0});
  context.engine.step(hp::Backend::SeekTimeUs-10);
  context.engine.step(hp::Backend::SeekTimeUs-9);
  take_trace(context.trace);
  context.engine.step(hp::Backend::SeekTimeUs);
  context.engine.step(2000);
  assert((take_trace(context.trace)==std::vector<std::string>{"D1","SC","D0","TO","D0","CM"}));
}
static void unsupported_command_tests() {
  Fixture f;
  take_trace(f.trace);
  assert(!strcmp(f.engine.last_error(),"none"));
  // A stale/unsupported command must not create extra attention bits, signal
  // completion, or clear control/status belonging to a real in-flight seek.
  f.bus.attention=1;
  const uint16_t before=f.bus.status[1];
  f.bus.command(15,1,{0,0,0}); f.engine.step(0);
  assert(f.bus.attention==1 && f.bus.status[1]==before);
  assert((take_trace(f.trace)==std::vector<std::string>{"D1","??","D1","E04"}));
  assert(f.engine.request_csr()==0x80 && f.engine.last_csr()==0x80);
  assert(f.engine.last_command()==0xf001 && f.engine.last_rar()==0);
  assert(!strcmp(f.engine.last_error(),"E04"));
  f.engine.step(1); assert(f.engine.last_csr()==0 && f.engine.request_csr()==0x80);
  // Preserve valid SEEK dispatch and its drive-zero completion after a bogus
  // drive-one request: the original bug would have added attention bit 1.
  f.bus.attention=0;
  f.bus.command(3,0,{0,0,0}); f.engine.step(2); f.engine.step(4002);
  assert(f.bus.attention==1);
  assert(f.engine.last_command()==0x3000 && f.engine.last_rar()==0);
}
int main() {
  static_assert(hp::ImageBytes==4988928);
  config_tests(); late_word_tests(); response_boundary_tests(); startup_seek_tests(); seek_geometry_tests(); seek_busy_recovery_tests(); read_tests(); write_tests();
  end_cylinder_and_errors(); check_data_tests(); pending_and_check_tests();
  reset_and_boundary_tests();
  trace_tests();
  unsupported_command_tests();
  puts("PASS: configuration, geometry, startup/POPIO refresh, concurrent seeks/abort, timer rollover, reads, writes, partial sectors, late-word discard/overrun/sector closing/SD stalls, EOC, media failures, pending commands, autonomous CHECK/48-49 sector boundaries, trace ordering, E01-E10 and queue overflow");
}
