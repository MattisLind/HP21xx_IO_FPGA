#include "backend.h"
#include <ctype.h>
#include <stdio.h>
#include <string.h>

namespace hp {
bool parse_config(const char *text, Config &config, char *error, size_t size) {
  Config next;
  bool seen[Drives] = {};
  unsigned line=0;
  auto fail = [&](const char *why) {
    snprintf(error, size, "line %u: %s", line, why);
    return false;
  };
  while (*text) {
    ++line;
    char row[128];
    unsigned n=0;
    while (*text && *text!='\n') {
      if (n+1>=sizeof(row)) return fail("line too long");
      row[n++]=*text++;
    }
    if (*text=='\n') ++text;
    row[n]=0;
    char *p=row;
    while (isspace(static_cast<unsigned char>(*p))) ++p;
    if (!*p || *p=='#' || *p==';') continue;
    char *eq=strchr(p, '=');
    if (!eq) return fail("expected drive0..drive3=filename");
    *eq++=0;
    char *end=p+strlen(p);
    while (end>p && isspace(static_cast<unsigned char>(end[-1]))) *--end=0;
    if (strlen(p)!=6 || strncmp(p,"drive",5) || p[5]<'0' || p[5]>'3')
      return fail("unknown key");
    const unsigned d=p[5]-'0';
    if (seen[d]) return fail("duplicate drive key");
    seen[d]=true;
    while (isspace(static_cast<unsigned char>(*eq))) ++eq;
    end=eq+strlen(eq);
    while (end>eq && isspace(static_cast<unsigned char>(end[-1]))) *--end=0;
    if (!*eq || !strcmp(eq,"none")) continue;
    if (strlen(eq)>=sizeof(next.image[d]) || strstr(eq,".."))
      return fail("invalid image filename");
    for (const char *c=eq; *c; ++c)
      if (!(isalnum(static_cast<unsigned char>(*c)) || *c=='.' || *c=='_' || *c=='-'))
        return fail("image must be a filename under /images");
    for (unsigned other=0; other<d; ++other)
      if (!strcmp(next.image[other],eq)) return fail("image assigned twice");
    // Also catch out-of-order keys. FAT names are case-insensitive.
    for (unsigned other=0; other<Drives; ++other) {
      const char *a=next.image[other], *b=eq;
      while (*a && *b && tolower(static_cast<unsigned char>(*a))==tolower(static_cast<unsigned char>(*b))) { ++a; ++b; }
      if (!*a && !*b) return fail("image assigned twice");
    }
    strcpy(next.image[d],eq);
  }
  config=next;
  if (size) error[0]=0;
  return true;
}
} // namespace hp
