#pragma once

// The hub's custom-endpoint fetch never trusts what the server says about its reply. It refuses a reply that is
// chunked, has no declared length, or declares more than the limit, and then copies at most limit + 1 bytes from the
// stream into a fixed buffer under an overall deadline, stopping the moment the reply goes over the limit, over its own
// declared length, or the deadline. Plain C++11, no Arduino: tests/workshop_os12_hub_body_limit_smoke.cpp runs it on the
// host against a fake stream.

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace workshop {
namespace http {

enum class BodyLength { Ok, Missing, TooLarge, Chunked };

// `size` is HTTPClient::getSize() (the Content-Length, or -1 when there is none); `transferEncoding` is whether the
// reply carried a Transfer-Encoding header at all (a reply with both that and a Content-Length is refused too: the
// length cannot be trusted).
inline BodyLength checkReplyHeaders(long size, bool transferEncoding, unsigned long limit) {
  if (transferEncoding) return BodyLength::Chunked;
  if (size < 0) return BodyLength::Missing;
  if (static_cast<unsigned long>(size) > limit) return BodyLength::TooLarge;
  return BodyLength::Ok;
}

enum class ReadStatus { Ok, TooLarge, OverDeclared, Timeout, Truncated };

struct ReadResult {
  ReadStatus status;
  std::size_t length;  // bytes in the buffer (valid when status is Ok)
};

// Source needs: int available(); int read(uint8_t* dst, std::size_t n); bool connected(); uint32_t nowMs(); void idle().
// `buf` holds at least limit + 1 bytes; the result is NUL-terminated at buf[length] when Ok.
template <class Source>
ReadResult readBounded(Source& s, long declared, unsigned long limit, uint32_t deadlineMs, char* buf) {
  const std::size_t cap = static_cast<std::size_t>(limit) + 1;  // one byte more than allowed, to see an overrun
  std::size_t total = 0;
  const uint32_t start = s.nowMs();
  for (;;) {
    // The deadline is checked on every pass, before anything else, so no stream behaviour can outlast it.
    if (static_cast<uint32_t>(s.nowMs() - start) > deadlineMs) return ReadResult{ReadStatus::Timeout, total};
    const int avail = s.available();
    if (avail > 0) {
      const std::size_t room = cap - total;
      const std::size_t want = static_cast<std::size_t>(avail) < room ? static_cast<std::size_t>(avail) : room;
      const int got = want ? s.read(reinterpret_cast<uint8_t*>(buf) + total, want) : 0;
      if (got <= 0) {  // it says bytes are there but gives none: wait a tick and let the deadline decide
        s.idle();
        continue;
      }
      total += static_cast<std::size_t>(got);
      if (total > limit) return ReadResult{ReadStatus::TooLarge, total};
      if (declared >= 0 && total > static_cast<std::size_t>(declared)) return ReadResult{ReadStatus::OverDeclared, total};
      continue;
    }
    if (declared >= 0 && total == static_cast<std::size_t>(declared)) {
      buf[total] = '\0';
      return ReadResult{ReadStatus::Ok, total};
    }
    if (!s.connected()) return ReadResult{ReadStatus::Truncated, total};
    s.idle();
  }
}

}  // namespace http
}  // namespace workshop
