#pragma once
#include <stdint.h>

namespace hp {
struct Media {
  virtual bool mount()=0;
  // Abandon stale handles, without flushing a removed/replaced card.
  virtual void unmount()=0;
  virtual bool healthy()=0;
  virtual bool faulted() const=0;
  virtual uint32_t now_ms(uint32_t sample) const { return sample; }
  virtual ~Media() = default;
};

// All card commands run only when the backend has no transfer, pending command,
// or seek worker. Scheduling uses milliseconds and survives timer rollover.
class MediaRecovery {
 public:
  enum Change { None, Mounted, Removed };
  explicit MediaRecovery(Media &media):media_(media) {}
  void begin(uint32_t now) { due_=now+StartupMs; }
  Change step(uint32_t now, bool busy) {
    if (busy) return None;
    if (mounted_ && media_.faulted()) return remove(now);
    if (int32_t(now-due_)<0) return None;
    if (mounted_) {
      due_=media_.now_ms(now)+ProbeMs;
      if (!media_.healthy()) return remove(now);
      return None;
    }
    ++attempts_;
    if (media_.mount()) {
      mounted_=true;
      consecutive_failures_=0;
      due_=media_.now_ms(now)+ProbeMs;
      return Mounted;
    }
    ++failures_;
    ++consecutive_failures_;
    due_=media_.now_ms(now)+(consecutive_failures_<FastAttempts ? RetryMs : OfflineRetryMs);
    return None;
  }
  bool mounted() const { return mounted_; }
  uint32_t attempts() const { return attempts_; }
  uint32_t failures() const { return failures_; }
  uint32_t removals() const { return removals_; }
  static constexpr uint32_t StartupMs=500, RetryMs=500, OfflineRetryMs=2000,
                            ProbeMs=1000, FastAttempts=5;
 private:
  Media &media_;
  bool mounted_=false;
  uint32_t due_=0, attempts_=0, failures_=0, removals_=0, consecutive_failures_=0;
  Change remove(uint32_t now) {
    media_.unmount();
    mounted_=false;
    consecutive_failures_=0;
    ++removals_;
    due_=media_.now_ms(now)+RetryMs;
    return Removed;
  }
};
} // namespace hp
