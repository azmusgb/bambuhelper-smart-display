#pragma once

// The hub's custom-endpoint fetch decides from the declared body length before it reads a byte: a reply over the
// limit, or one with no declared length (chunked, or a connection close), is refused rather than buffered. Plain C++11,
// no Arduino, so tests/workshop_os12_hub_body_limit_smoke.cpp checks it on the host.

namespace workshop {
namespace http {

enum class BodyLength { Ok, Missing, TooLarge };

// `size` is HTTPClient::getSize(): the Content-Length, or -1 when the reply has none.
inline BodyLength checkBodyLength(long size, unsigned long limit) {
  if (size < 0) return BodyLength::Missing;
  if (static_cast<unsigned long>(size) > limit) return BodyLength::TooLarge;
  return BodyLength::Ok;
}

}  // namespace http
}  // namespace workshop
