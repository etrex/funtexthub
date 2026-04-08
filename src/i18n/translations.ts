export const supportedLangs = ['zh-tw', 'en'] as const;
export type Lang = typeof supportedLangs[number];
export const defaultLang: Lang = 'zh-tw';

export const langNames: Record<Lang, string> = {
  'zh-tw': '繁體中文',
  'en': 'English',
};

export const ui: Record<Lang, Record<string, string>> = {
  'zh-tw': {
    site_name: 'FunTextHub',
    site_tagline: '每日精選趣味文案，笑話、語錄、情話一次看',
    hero_subtitle: '網路最夯的笑話、暖心語錄、土味情話，每日更新，讓你隨時都有梗可以用！',
    all_topics: '所有主題',
    all_categories: '全部',
    random_btn: '隨機一則',
    items_count: '則收錄',
    last_updated: '最後更新',
    editor_note: '使用場景',
    variations: '延伸版本',
    more_topics: '更多主題推薦',
    share_copy: '複製內容',
    share_copied: '已複製！',
    tag_filter: '標籤篩選',
    daily_picks: '今日精選',
    nav_home: '首頁',
    nav_topics: '所有主題',
    privacy: '隱私權政策',
    terms: '服務條款',
    about: '關於我們',
    disclaimer: '本站內容為編輯團隊蒐集整理，如有侵權疑慮請聯繫我們下架。',
    dmca_contact: '侵權通知請寄：',
    back_home: '← 返回首頁',
    page_of: '第 {current} 頁，共 {total} 頁',
    prev_page: '上一頁',
    next_page: '下一頁',
  },
  'en': {
    site_name: 'FunTextHub',
    site_tagline: 'Daily curated fun texts - jokes, quotes & pickup lines',
    hero_subtitle: 'The best jokes, heartwarming quotes, and cheesy pickup lines from across the internet, updated daily!',
    all_topics: 'All Topics',
    all_categories: 'All',
    random_btn: 'Random Pick',
    items_count: 'items',
    last_updated: 'Last updated',
    editor_note: 'Best used for',
    variations: 'Variations',
    more_topics: 'More Topics',
    share_copy: 'Copy',
    share_copied: 'Copied!',
    tag_filter: 'Filter by tag',
    daily_picks: "Today's Picks",
    nav_home: 'Home',
    nav_topics: 'All Topics',
    privacy: 'Privacy Policy',
    terms: 'Terms of Service',
    about: 'About Us',
    disclaimer: 'Content is curated and edited by our team. If you believe any content infringes your rights, please contact us for removal.',
    dmca_contact: 'DMCA notices:',
    back_home: '← Back to Home',
    page_of: 'Page {current} of {total}',
    prev_page: 'Previous',
    next_page: 'Next',
  },
};

export function useTranslations(lang: Lang) {
  return function t(key: string): string {
    return ui[lang]?.[key] ?? ui[defaultLang]?.[key] ?? key;
  };
}

export function getI18n(i18nObj: Record<string, any> | undefined, lang: Lang): any {
  if (!i18nObj) return undefined;
  const preferred = i18nObj[lang];
  if (preferred && Object.values(preferred).some((v: any) => v && v !== '')) return preferred;
  const fallback = i18nObj[defaultLang];
  if (fallback && Object.values(fallback).some((v: any) => v && v !== '')) return fallback;
  for (const l of supportedLangs) {
    const alt = i18nObj[l];
    if (alt && Object.values(alt).some((v: any) => v && v !== '')) return alt;
  }
  return undefined;
}
