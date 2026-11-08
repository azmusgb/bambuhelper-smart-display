// The hub's custom-endpoint fetch trusts nothing the server says about its reply.
// Host test for baseline/files/include/workshop_http_body_limit.hpp.
#include "../baseline/files/include/workshop_http_body_limit.hpp"

#include <cassert>
#include <string>
#include <vector>

using namespace workshop::http;

namespace {

const unsigned long kLimit = 4096;

// A fake socket: `data` arrives in `chunk`-byte pieces, one piece per idle() tick after the first; time moves 1 ms per
// idle(); `stall` stops any data (a server that stops sending).
struct Fake {
  std::string data;
  std::size_t pos = 0, chunk = 0, ready = 0;
  bool open = true, stall = false;
  uint32_t t = 0;
  std::size_t reads = 0, readBytes = 0;
  Fake(const std::string& d, std::size_t c) : data(d), chunk(c ? c : d.size()), ready(c ? c : d.size()) {}
  int available() { return stall ? 0 : static_cast<int>((ready < data.size() ? ready : data.size()) - pos); }
  int read(uint8_t* dst, std::size_t n) {
    std::size_t have = static_cast<std::size_t>(available());
    std::size_t k = n < have ? n : have;
    std::memcpy(dst, data.data() + pos, k);
    pos += k; ++reads; readBytes += k;
    return static_cast<int>(k);
  }
  bool connected() { return open && pos < data.size() ? true : (open && !stall); }
  uint32_t nowMs() { return t; }
  void idle() { ++t; ready += chunk; if (ready > data.size() && pos >= data.size()) open = false; }
};

std::string text(std::size_t n) { return std::string(n, 'x'); }

void headers() {
  assert(checkReplyHeaders(1, false, kLimit) == BodyLength::Ok);
  assert(checkReplyHeaders(4096, false, kLimit) == BodyLength::Ok);
  assert(checkReplyHeaders(0, false, kLimit) == BodyLength::Ok);
  assert(checkReplyHeaders(4097, false, kLimit) == BodyLength::TooLarge);
  assert(checkReplyHeaders(2147483647L, false, kLimit) == BodyLength::TooLarge);
  assert(checkReplyHeaders(-1, false, kLimit) == BodyLength::Missing);
  // Content-Length AND Transfer-Encoding: refused, whatever the length says (the length cannot be trusted).
  assert(checkReplyHeaders(100, true, kLimit) == BodyLength::Chunked);
  assert(checkReplyHeaders(-1, true, kLimit) == BodyLength::Chunked);
  assert(checkReplyHeaders(0, true, kLimit) == BodyLength::Chunked);
}

void honestReplies() {
  std::vector<char> buf(kLimit + 1);
  {  // exactly the declared length, in one piece
    Fake f(text(200), 0);
    ReadResult r = readBounded(f, 200, kLimit, 4500, buf.data());
    assert(r.status == ReadStatus::Ok && r.length == 200 && buf[200] == '\0');
  }
  {  // exactly the limit, in small pieces
    Fake f(text(4096), 100);
    ReadResult r = readBounded(f, 4096, kLimit, 4500, buf.data());
    assert(r.status == ReadStatus::Ok && r.length == 4096);
  }
  {  // empty body
    Fake f("", 0);
    ReadResult r = readBounded(f, 0, kLimit, 4500, buf.data());
    assert(r.status == ReadStatus::Ok && r.length == 0);
  }
}

void overDeclared() {
  // Declares 10 bytes, sends far more at once: refused, and never more than limit + 1 bytes were copied.
  std::vector<char> buf(kLimit + 1 + 64, 'Z');  // guard bytes after the buffer proper
  Fake f(text(100000), 0);
  ReadResult r = readBounded(f, 10, kLimit, 4500, buf.data());
  assert(r.status == ReadStatus::OverDeclared || r.status == ReadStatus::TooLarge);
  assert(f.readBytes <= kLimit + 1);
  for (std::size_t i = kLimit + 1; i < buf.size(); ++i) assert(buf[i] == 'Z');
}

void overLimit() {
  // Declares 100 but the stream carries a huge body (declared length is wrong): the copy stops at limit + 1.
  std::vector<char> buf(kLimit + 1 + 64, 'Z');
  Fake f(text(1000000), 700);
  ReadResult r = readBounded(f, 100, kLimit, 4500, buf.data());
  assert(r.status == ReadStatus::OverDeclared || r.status == ReadStatus::TooLarge);
  assert(f.readBytes <= kLimit + 1);
  for (std::size_t i = kLimit + 1; i < buf.size(); ++i) assert(buf[i] == 'Z');
  // Declares the limit exactly but sends one byte more: TooLarge or OverDeclared, never accepted.
  Fake g(text(4097), 0);
  r = readBounded(g, 4096, kLimit, 4500, buf.data());
  assert(r.status != ReadStatus::Ok);
}

void stallsAndTruncation() {
  std::vector<char> buf(kLimit + 1);
  {  // the server stops sending before the declared length: the deadline ends the read
    Fake f(text(50), 0);
    f.stall = true;
    ReadResult r = readBounded(f, 50, kLimit, 4500, buf.data());
    assert(r.status == ReadStatus::Timeout);
    assert(f.t > 4500);
  }
  {  // a slow drip that never finishes inside the deadline
    Fake f(text(3000), 1);
    ReadResult r = readBounded(f, 3000, kLimit, 1000, buf.data());
    assert(r.status == ReadStatus::Timeout);
  }
  {  // the connection closes early
    Fake f(text(20), 0);
    f.open = false;
    f.data = text(20);
    f.pos = 20;
    ReadResult r = readBounded(f, 50, kLimit, 4500, buf.data());
    assert(r.status == ReadStatus::Truncated);
  }
}

// A stream that keeps saying bytes are available but never gives one (read() returns 0, or less): the deadline still ends it.
struct Liar {
  int answer;
  uint32_t t = 0;
  std::size_t reads = 0;
  explicit Liar(int a) : answer(a) {}
  int available() { return 10; }
  int read(uint8_t*, std::size_t) { ++reads; return answer; }
  bool connected() { return true; }
  uint32_t nowMs() { return t; }
  void idle() { ++t; }
};

void availableButReadsNothing() {
  std::vector<char> buf(kLimit + 1);
  for (int answer : {0, -1}) {
    Liar f(answer);
    ReadResult r = readBounded(f, 50, kLimit, 4500, buf.data());
    assert(r.status == ReadStatus::Timeout);
    assert(f.t > 4500 && f.t <= 4502);  // it stopped at the deadline, not long after
    assert(r.length == 0);
  }
}

}  // namespace

int main() {
  headers();
  honestReplies();
  overDeclared();
  overLimit();
  stallsAndTruncation();
  availableButReadsNothing();
  return 0;
}
