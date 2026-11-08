// The hub's custom-endpoint fetch must decide from the declared length before it reads the body.
// Host test for baseline/files/include/workshop_http_body_limit.hpp.
#include "../baseline/files/include/workshop_http_body_limit.hpp"

#include <cassert>

using workshop::http::BodyLength;
using workshop::http::checkBodyLength;

int main() {
    const unsigned long limit = 4096;
    // Within the limit, including exactly the limit and an empty body.
    assert(checkBodyLength(1, limit) == BodyLength::Ok);
    assert(checkBodyLength(4096, limit) == BodyLength::Ok);
    assert(checkBodyLength(0, limit) == BodyLength::Ok);
    // Over the limit is rejected before any byte is read.
    assert(checkBodyLength(4097, limit) == BodyLength::TooLarge);
    assert(checkBodyLength(2147483647L, limit) == BodyLength::TooLarge);
    // A missing length (HTTPClient's -1 for a chunked or unterminated reply) is rejected: the size is not known.
    assert(checkBodyLength(-1, limit) == BodyLength::Missing);
    assert(checkBodyLength(-2, limit) == BodyLength::Missing);
    return 0;
}
