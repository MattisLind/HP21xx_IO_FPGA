#include "media.h"
#include <assert.h>
#include <stdio.h>

struct Card : hp::Media {
  unsigned mounts=0, unmounts=0, probes=0, failures=0;
  bool present=true, io_failed=false;
  uint32_t elapsed=0;
  bool mount() override { ++mounts; return present && mounts>failures; }
  void unmount() override { ++unmounts; io_failed=false; }
  bool healthy() override { ++probes; return present; }
  bool faulted() const override { return io_failed; }
  uint32_t now_ms(uint32_t sample) const override { return sample+elapsed; }
};

int main() {
  Card card; card.failures=2;
  hp::MediaRecovery media(card); media.begin(100);
  assert(media.step(599,false)==hp::MediaRecovery::None && !card.mounts);
  media.step(600,false); media.step(1099,false);
  assert(card.mounts==1);
  media.step(1100,false);
  assert(media.step(1600,true)==hp::MediaRecovery::None && card.mounts==2);
  assert(media.step(1600,false)==hp::MediaRecovery::Mounted);
  assert(media.mounted() && media.attempts()==3 && media.failures()==2);
  card.present=false;
  media.step(2600,true); assert(!card.probes && media.mounted());
  assert(media.step(2600,false)==hp::MediaRecovery::Removed);
  assert(card.unmounts==1 && !media.mounted());
  media.step(3099,false); assert(card.mounts==3);
  media.step(3100,false); assert(card.mounts==4 && !media.mounted());
  card.present=true;
  assert(media.step(3600,false)==hp::MediaRecovery::Mounted);
  card.io_failed=true;
  media.step(3601,true); assert(card.unmounts==1);
  assert(media.step(3601,false)==hp::MediaRecovery::Removed);
  assert(card.unmounts==2 && media.removals()==2);
  assert(media.step(4101,false)==hp::MediaRecovery::Mounted);

  // Absence at startup cannot spin on SD initialization: fast attempts are
  // limited, followed by one attempt per two seconds, including tick wrap.
  Card absent; absent.present=false;
  hp::MediaRecovery retry(absent); retry.begin(0xfffffe0cU); // +500 wraps to zero
  retry.step(0xffffffffU,false); assert(!absent.mounts);
  for (uint32_t now=0; now<=2000; now+=500) retry.step(now,false);
  assert(absent.mounts==5);
  retry.step(3999,false); assert(absent.mounts==5);
  absent.present=true;
  assert(retry.step(4000,false)==hp::MediaRecovery::Mounted);
  retry.step(4999,false); assert(!absent.probes);
  retry.step(5000,false); assert(absent.probes==1);
  Card slow; slow.failures=1; slow.elapsed=1200;
  hp::MediaRecovery delayed(slow); delayed.begin(0);
  delayed.step(500,false);
  delayed.step(2199,false); assert(slow.mounts==1);
  assert(delayed.step(2200,false)==hp::MediaRecovery::Mounted);
  puts("PASS: startup retries/backoff, absent card, reinsertion, idle-only probes, I/O faults and timer wrap");
}
