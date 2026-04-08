# FunTextHub Agent Instructions

## Website Overview
- **URL**: funtexthub.com (Cloudflare Pages: funtexthub.pages.dev)
- **Purpose**: Curated collection of fun text content — jokes, sweet quotes, cheesy pickup lines, and more
- **Tech**: Astro (Static) + Tailwind CSS v4
- **Deployment**: Cloudflare Pages (wrangler deploy)
- **Languages**: Traditional Chinese `/zh-tw/` + English `/en/`
- **Cloudflare Account ID**: 8c4a53bddc1c11f46aa4709db491265d

## Content Schema

All topic files are stored in `src/content/topics/` as JSON files.

### Topic JSON Structure (Mandatory)
```json
{
  "slug": "kebab-case-topic-name",
  "category": "Category Name",
  "i18n": {
    "zh-tw": { "title": "中文標題", "description": "中文描述" },
    "en": { "title": "English Title", "description": "English description" }
  },
  "items": [
    {
      "id": "unique-id",
      "dateAdded": "YYYY-MM-DD",
      "sourceUrl": "https://source-reference-url",
      "sourceNote": "source description (internal only, not displayed)",
      "tags": ["tag1", "tag2"],
      "i18n": {
        "zh-tw": {
          "content": "內容文字",
          "editorNote": "使用場景建議",
          "variations": ["延伸版本1"]
        },
        "en": {
          "content": "Content text",
          "editorNote": "Usage scenario",
          "variations": ["Variation 1"]
        }
      }
    }
  ]
}
```

## Content Rewriting Rules

**CRITICAL: All content must be rewritten, never copy-pasted.**

1. **Keep the core value**: Preserve the punchline, emotional core, or key insight
2. **Change surface details**: Replace character names, settings, specific objects
3. **Rewrite expressions**: Use different wording to convey the same meaning
4. **Add original value**: Include editorNote (usage scenarios) and variations
5. **sourceUrl/sourceNote**: Record internally for reference, NOT displayed on site
6. **No attribution text**: Do not write "改編自" or "adapted from" in the content

## Writing Style

### Traditional Chinese (zh-tw)
- 口語化、自然的台灣用語
- 笑話保持簡短，節奏明快
- 語錄要有溫度但不矯情
- 情話要土但不低俗
- 不使用簡體字或中國大陸用語
- 標點符號用全形

### English
- Casual, conversational tone
- Keep jokes punchy and concise
- Quotes should feel genuine, not saccharine
- Pickup lines should be cheesy but clean
- Use American English spelling

## ID Convention
- Format: `{topic-prefix}-{3-digit-number}`
- Examples: `cj-001` (cold jokes), `sq-001` (sweet quotes), `cp-001` (cheesy pickups)
- Always check existing IDs before creating new ones to avoid duplicates

## Category List
Current categories:
- Humor (笑話類)
- Romance (戀愛類)
- Motivation (勵志類)
- Social (社交類)
- Lifestyle (生活類)

## Build & Deploy
```bash
cd /Users/etrexkuo/Documents/github/funtexthub
npm run build
CLOUDFLARE_ACCOUNT_ID=8c4a53bddc1c11f46aa4709db491265d npx wrangler pages deploy dist --project-name funtexthub --branch main
git add -A && git commit -m "content: <action description>" && git push
```

## Quality Checklist
- [ ] Both zh-tw and en content provided for every item
- [ ] Content is rewritten (not copy-pasted from source)
- [ ] editorNote provides useful usage context
- [ ] Tags are relevant and consistent with existing tags
- [ ] IDs are unique and follow convention
- [ ] No duplicate content across items
- [ ] Build succeeds before deploying
