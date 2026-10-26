#include "backend.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <vector>
#include <string>

struct Bus : hp::Bus {
  uint16_t csr=0, cmd=0, rar=0, word=0, attention=0, status[4]={};
  std::vector<uint16_t> output;
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
    else if (reg==hp::Attention) attention|=value;
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
static void read_tests() {
  Fixture f;
  f.images.bytes[0][0]=0x34; f.images.bytes[0][1]=0x12;
  f.bus.command(2,0,{0,0,0}); f.engine.step(0);
  assert(f.images.reads==1);
  f.engine.step(1); assert(f.bus.output.back()==0x1234);
  // No further filesystem calls in the word handshake.
  for (unsigned i=0;i<127;++i) { f.bus.csr|=0x40; f.engine.step(i+2); }
  assert(f.bus.output.size()==128 && f.images.reads==1);
  f.engine.step(300); assert(!f.engine.active() && f.bus.attention==1);
  assert(f.images.writes==0);
}
static void write_tests() {
  Fixture f;
  f.bus.command(1,0,{0,0,0}); f.engine.step(0);
  f.bus.input(0x1234); f.engine.step(1);
  f.bus.input(0xabcd); f.engine.step(2);
  f.engine.step(103);
  assert(!f.engine.active() && f.images.written==256);
  assert(f.images.bytes[0][0]==0x34 && f.images.bytes[0][1]==0x12);
  assert(f.images.bytes[0][2]==0xcd && f.images.bytes[0][3]==0xab);
  for (unsigned i=4;i<256;++i) assert(f.images.bytes[0][i]==0);
  assert(f.images.bytes[0][256]==0x5a); // Following sectors unchanged.
  // Completed sectors plus a partial one are persisted, without truncating.
  f.bus.command(1,0,{0,0,1}); f.engine.step(200);
  for (unsigned i=0;i<129;++i) { f.bus.input(uint16_t(i)); f.engine.step(201+i); }
  f.engine.step(500); assert(f.images.written==512);
  assert(f.images.bytes[0][256]==0 && f.images.bytes[0][258]==1);
  assert(f.images.bytes[0][768]==0x5a);
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
  f.bus.input(0xbeef); f.engine.step(5001); f.engine.step(5200);
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
  f.engine.step(4001); f.engine.step(4200); assert(!f.engine.active());
  f.bus.command(6,0,{1,0,0}); f.engine.step(5000);
  f.bus.input(1); f.engine.step(5001); // One sector to check.
  f.engine.step(5002);
  for (unsigned i=0;i<128;++i) { f.bus.csr|=0x40; f.engine.step(5003+i); }
  assert(!f.engine.active() && f.bus.output.back()==0);
  // A command during a stream is captured despite CSR's destructive read.
  Fixture q;
  q.bus.command(2,0,{0,0,0}); q.engine.step(0); q.engine.step(1);
  q.bus.command(3,1,{7,0,0}); q.engine.step(2);
  q.engine.step(200); q.engine.step(201); q.engine.step(4201);
  assert(q.bus.attention&2);
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
  f.bus.input(0xabcd); f.engine.step(1); f.engine.step(102);
  assert((take_trace(f.trace)==std::vector<std::string>{"D0","WR","D0","TO","D0","ZF","D0","CM"}));
  assert(f.engine.errors()==0); // Normal short-transfer timeout is not an error.
  f.bus.command(2,3,{0,0,0}); f.engine.step(200);
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
  media.bus.input(123); media.engine.step(2); media.engine.step(103);
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
  context.engine.step(hp::Backend::SeekTimeUs+hp::Backend::WordTimeoutUs);
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
  config_tests(); startup_seek_tests(); read_tests(); write_tests();
  end_cylinder_and_errors(); pending_and_check_tests();
  reset_and_boundary_tests();
  trace_tests();
  unsupported_command_tests();
  puts("PASS: configuration, geometry, startup/POPIO refresh, concurrent seeks/abort, timer rollover, reads, writes, partial sectors, EOC, media failures, pending commands, check-data, trace ordering, E01-E10 and queue overflow");
}
