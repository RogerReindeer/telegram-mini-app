/**
 * MiniApp Sync
 * Основная таблица → MiniApp Google Sheets → Supabase.
 *
 * Все настройки находятся в одном блоке ниже.
 * Вставьте значения между кавычками и больше ничего в коде менять не нужно.
 */

/* =========================================================
 * НАСТРОЙКИ
 * ========================================================= */

// ID основной таблицы с листами Legend / Chapters / fox.
const SOURCE_SPREADSHEET_ID = 'ВСТАВЬТЕ_ID_ОСНОВНОЙ_ТАБЛИЦЫ';

// ID отдельной таблицы MiniApp.
// В неё будут записываться листы MiniAppNovels, MiniAppChapters и fox.
// Если отдельная таблица не нужна, оставьте пустую строку: ''.
const MINIAPP_SHEET_ID = 'ВСТАВЬТЕ_ID_ТАБЛИЦЫ_MINIAPP';

// Базовый адрес сайта Render — без /library и без /api/sync.
const MINIAPP_SITE_URL = 'https://ВАШ-СЕРВИС.onrender.com';

// Должен полностью совпадать с Render → Environment → SYNC_TOKEN.
const MINIAPP_SYNC_TOKEN = 'ВСТАВЬТЕ_SYNC_TOKEN';

// Часовой пояс для преобразования дат.
const MINIAPP_TIMEZONE = 'Europe/Moscow';

/* =========================================================
 * СЛУЖЕБНЫЕ НАСТРОЙКИ
 * Ниже этого блока значения обычно менять не требуется.
 * ========================================================= */

const MINIAPP_SYNC = Object.freeze({
  ENDPOINT_PATH: '/api/sync',
  HEALTH_PATH: '/health',

  NOVEL_SHEETS: ['MiniAppNovels', 'Novels', 'Legend'],
  CHAPTER_SHEETS: ['MiniAppChapters', 'Chapters'],
  FOX_SHEETS: ['fox', 'Fox'],

  TARGET_NOVEL_SHEET: 'MiniAppNovels',
  TARGET_CHAPTER_SHEET: 'MiniAppChapters',
  TARGET_FOX_SHEET: 'fox',

  MAX_RESPONSE_TEXT: 1800,
});

const MINIAPP_NOVEL_EXPORT_HEADERS = Object.freeze([
  'NovelID',
  'Slug',
  'NovelShort',
  'NovelTitleRu',
  'NovelTitleEn',
  'PostIcons',
  'CoverURL',
  'Description',
  'Tags',
  'TopDescription',
  'BottomDescription',
  'OriginalLanguage',
  'TotalChapters',
  'TranslatedChapters',
  'ProgressPercent',
  'Status',
  'AccessModel',
  'ScheduleMode',
  'EarlyAccessMode',
  'SortOrder',
  'IsVisible',
  'AgeRating',
  'HasAdultBadge',
  'TranslationStatus',
  'TranslationStatusLabel',
  'TranslationStatusColor',
  'RelationType',
  'RelationIcon',
  'RelationColor',
  'TagsShort',
  'TagsTooltip',
  'AddedDate',
  'TranslationAuthor',
]);

const MINIAPP_CHAPTER_EXPORT_HEADERS = Object.freeze([
  'ChapterID',
  'NovelID',
  'ChapterNo',
  'ChapterTitle',
  'Slug',
  'Volume',
  'VolumeNo',
  'VolumeTitle',
  'TranslationDate',
  'ReleaseDate',
  'FreeReleaseDate',
  'PremiumReleaseDate',
  'TelegraphURL',
  'TelegraphFreeURL',
  'TelegraphPremiumURL',
  'TelegraphFreeCode',
  'TelegraphPremiumCode',
  'SourceType',
  'AccessLevel',
  'IsVisible',
  'SortOrder',
]);

const MINIAPP_FOX_EXPORT_HEADERS = Object.freeze([
  'name',
  'url',
]);


/**
 * Показывает текущие настройки без вывода секретного токена.
 * Значения меняются только в блоке «НАСТРОЙКИ» в начале файла.
 */
function configureMiniAppSync() {
  const config = miniAppGetConfig_();
  const targetText = config.targetSpreadsheetId
    ? config.targetSpreadsheetId
    : 'отдельная MiniApp-таблица отключена';

  SpreadsheetApp.getUi().alert(
    'Настройки MiniApp',
    [
      'Источник: ' + config.sourceSpreadsheetId,
      'MiniApp-таблица: ' + targetText,
      'Сайт: ' + config.siteUrl,
      'Endpoint: ' + config.siteUrl + MINIAPP_SYNC.ENDPOINT_PATH,
      'Часовой пояс: ' + config.timezone,
      '',
      'Чтобы изменить настройки, отредактируйте блок «НАСТРОЙКИ» в начале файла.',
    ].join('\n'),
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

/**
 * Проверяет, что Render отвечает и используется правильный базовый URL.
 */
function checkMiniAppSiteConnection() {
  const config = miniAppGetConfig_();
  const url = config.siteUrl + MINIAPP_SYNC.HEALTH_PATH;

  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    muteHttpExceptions: true,
    followRedirects: true,
    headers: {
      Accept: 'application/json',
    },
  });

  const code = response.getResponseCode();
  const body = response.getContentText('UTF-8');

  if (code < 200 || code >= 300) {
    throw new Error(
      'Сайт не прошёл проверку.\n' +
        'URL: ' + url + '\n' +
        'HTTP: ' + code + '\n' +
        miniAppShortText_(body)
    );
  }

  const data = miniAppParseJson_(body, 'Проверка /health вернула не JSON.');
  if (data.status !== 'ok') {
    throw new Error('Сайт ответил, но статус не ok:\n' + miniAppShortText_(body));
  }

  SpreadsheetApp.getUi().alert(
    'Соединение работает',
    'Сайт доступен:\n' + config.siteUrl + '\n\n' +
      'Синхронизация будет отправляться на:\n' +
      config.siteUrl + MINIAPP_SYNC.ENDPOINT_PATH,
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

/**
 * Главная функция из меню MiniApp.
 * Читает книги, главы и лисичек из таблицы и отправляет JSON на сайт.
 */
function syncMiniAppSiteData() {
  const lock = LockService.getDocumentLock();

  if (!lock.tryLock(30000)) {
    throw new Error('Синхронизация уже запущена в другом окне. Попробуйте позже.');
  }

  try {
    const activeSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();
    const config = miniAppGetConfig_();
    const sourceSpreadsheet = SpreadsheetApp.openById(config.sourceSpreadsheetId);

    SpreadsheetApp.flush();
    activeSpreadsheet.toast('Собираю данные для MiniApp…', 'MiniApp', 5);

    const novelSheet = miniAppFindSheet_(
      sourceSpreadsheet,
      MINIAPP_SYNC.NOVEL_SHEETS,
      true
    );
    const chapterSheet = miniAppFindSheet_(
      sourceSpreadsheet,
      MINIAPP_SYNC.CHAPTER_SHEETS,
      true
    );
    const foxSheet = miniAppFindSheet_(
      sourceSpreadsheet,
      MINIAPP_SYNC.FOX_SHEETS,
      false
    );

    const rawNovels = miniAppReadSheetObjects_(novelSheet);
    const rawChapters = miniAppReadSheetObjects_(chapterSheet);
    const rawFox = foxSheet ? miniAppReadSheetObjects_(foxSheet) : [];

    const novels = rawNovels
      .map(row => miniAppMapNovelRow_(row, novelSheet.getName()))
      .filter(row => miniAppHasValue_(row.NovelID) && miniAppHasValue_(row.NovelShort || row.Title));

    const chapters = rawChapters
      .map(miniAppMapChapterRow_)
      .filter(row => miniAppHasValue_(row.ChapterID) && miniAppHasValue_(row.NovelID));

    const fox = rawFox
      .map(miniAppMapFoxRow_)
      .filter(row => miniAppHasValue_(row.name) && miniAppHasValue_(row.url));

    miniAppValidatePayload_(novels, chapters, fox, novelSheet, chapterSheet, foxSheet);

    if (config.targetSpreadsheetId) {
      miniAppWriteTargetSpreadsheet_(
        config.targetSpreadsheetId,
        novels,
        chapters,
        fox
      );
    }

    const payload = {
      novels: novels,
      chapters: chapters,
      fox: fox,
      meta: {
        spreadsheet_id: sourceSpreadsheet.getId(),
        spreadsheet_name: sourceSpreadsheet.getName(),
        sent_at: new Date().toISOString(),
        source_sheets: {
          novels: novelSheet.getName(),
          chapters: chapterSheet.getName(),
          fox: foxSheet ? foxSheet.getName() : '',
        },
      },
    };

    activeSpreadsheet.toast(
      'Отправляю: книг ' + novels.length + ', глав ' + chapters.length + ', лисичек ' + fox.length,
      'MiniApp',
      8
    );

    const result = miniAppPostPayload_(config, payload);

    const message = [
      'Сайт успешно синхронизирован.',
      '',
      'Книги: ' + miniAppResultCount_(result, 'novels_upserted', novels.length),
      'Главы: ' + miniAppResultCount_(result, 'chapters_upserted', chapters.length),
      'Лисички: ' + miniAppResultCount_(result, 'fox_upserted', fox.length),
      '',
      'Источник книг: ' + novelSheet.getName(),
      'Источник глав: ' + chapterSheet.getName(),
      'Источник лисичек: ' + (foxSheet ? foxSheet.getName() : 'не найден'),
    ].join('\n');

    activeSpreadsheet.toast('Синхронизация завершена.', 'MiniApp', 5);
    SpreadsheetApp.getUi().alert('MiniApp', message, SpreadsheetApp.getUi().ButtonSet.OK);
  } catch (error) {
    const message = error && error.message ? error.message : String(error);
    console.error('MiniApp sync error:', error && error.stack ? error.stack : error);

    SpreadsheetApp.getActiveSpreadsheet().toast(
      'Синхронизация не выполнена.',
      'MiniApp: ошибка',
      8
    );

    SpreadsheetApp.getUi().alert(
      'MiniApp: синхронизация не выполнена',
      message,
      SpreadsheetApp.getUi().ButtonSet.OK
    );

    throw error;
  } finally {
    lock.releaseLock();
  }
}

/**
 * Удаляет сохранённые настройки подключения.
 */
function resetMiniAppSyncConfig() {
  SpreadsheetApp.getUi().alert(
    'Настройки MiniApp находятся в начале файла и автоматически не удаляются.'
  );
}

/**
 * Можно вызвать из существующего onOpen().
 * Не создавайте второй onOpen — это может сломать ваше меню «Релизы».
 */
function addMiniAppMenu_() {
  SpreadsheetApp.getUi()
    .createMenu('MiniApp')
    .addItem('Показать настройки', 'configureMiniAppSync')
    .addItem('Проверить соединение', 'checkMiniAppSiteConnection')
    .addSeparator()
    .addItem('Обновить MiniApp и сайт', 'syncMiniAppSiteData')
    .addToUi();
}

function miniAppGetConfig_() {
  const sourceSpreadsheetId = miniAppNormalizeSpreadsheetId_(
    SOURCE_SPREADSHEET_ID
  );
  const targetSpreadsheetId = miniAppNormalizeSpreadsheetId_(
    MINIAPP_SHEET_ID
  );
  const siteUrl = miniAppNormalizeBaseUrl_(MINIAPP_SITE_URL);
  const syncToken = String(MINIAPP_SYNC_TOKEN || '').trim();
  const timezone = String(MINIAPP_TIMEZONE || '').trim() || 'Europe/Moscow';

  if (!sourceSpreadsheetId) {
    throw new Error(
      'Не заполнен SOURCE_SPREADSHEET_ID в блоке «НАСТРОЙКИ» в начале файла.'
    );
  }

  if (!siteUrl) {
    throw new Error(
      'Не заполнен MINIAPP_SITE_URL в блоке «НАСТРОЙКИ» в начале файла.'
    );
  }

  if (!syncToken || syncToken === 'ВСТАВЬТЕ_SYNC_TOKEN') {
    throw new Error(
      'Не заполнен MINIAPP_SYNC_TOKEN в блоке «НАСТРОЙКИ» в начале файла.'
    );
  }

  if (
    targetSpreadsheetId &&
    targetSpreadsheetId === sourceSpreadsheetId
  ) {
    throw new Error(
      'SOURCE_SPREADSHEET_ID и MINIAPP_SHEET_ID не должны совпадать. ' +
        'Иначе экспорт может перезаписать исходные данные.'
    );
  }

  return {
    sourceSpreadsheetId: sourceSpreadsheetId,
    targetSpreadsheetId: targetSpreadsheetId,
    siteUrl: siteUrl,
    syncToken: syncToken,
    timezone: timezone,
  };
}

function miniAppNormalizeSpreadsheetId_(value) {
  const text = String(value || '').trim();

  if (
    !text ||
    /^ВСТАВЬТЕ_/i.test(text)
  ) {
    return '';
  }

  const match = text.match(/\/spreadsheets\/d\/([a-zA-Z0-9-_]+)/);
  return match ? match[1] : text;
}

function miniAppNormalizeBaseUrl_(value) {
  let url = String(value || '').trim();
  if (!url) return '';

  if (!/^https?:\/\//i.test(url)) {
    url = 'https://' + url;
  }

  url = url.replace(/\/+$/, '');

  // Если случайно вставили старый или полный endpoint, оставляем только базовый домен.
  url = url.replace(/\/(?:admin\/sync-from-sheets|api\/sync|sync)$/i, '');
  url = url.replace(/\/(?:library|health)$/i, '');
  url = url.replace(/\/+$/, '');

  if (!/^https:\/\//i.test(url)) {
    throw new Error('Для сайта MiniApp требуется HTTPS-адрес.');
  }

  return url;
}


function miniAppWriteTargetSpreadsheet_(
  targetSpreadsheetId,
  novels,
  chapters,
  fox
) {
  const targetSpreadsheet = SpreadsheetApp.openById(targetSpreadsheetId);

  miniAppWriteObjectsToSheet_(
    targetSpreadsheet,
    MINIAPP_SYNC.TARGET_NOVEL_SHEET,
    MINIAPP_NOVEL_EXPORT_HEADERS,
    novels
  );

  miniAppWriteObjectsToSheet_(
    targetSpreadsheet,
    MINIAPP_SYNC.TARGET_CHAPTER_SHEET,
    MINIAPP_CHAPTER_EXPORT_HEADERS,
    chapters
  );

  miniAppWriteObjectsToSheet_(
    targetSpreadsheet,
    MINIAPP_SYNC.TARGET_FOX_SHEET,
    MINIAPP_FOX_EXPORT_HEADERS,
    fox
  );

  SpreadsheetApp.flush();
}

function miniAppWriteObjectsToSheet_(
  spreadsheet,
  sheetName,
  headers,
  rows
) {
  let sheet = spreadsheet.getSheetByName(sheetName);

  if (!sheet) {
    sheet = spreadsheet.insertSheet(sheetName);
  }

  const requiredRows = Math.max(rows.length + 1, 2);
  const requiredColumns = Math.max(headers.length, 1);

  if (sheet.getMaxRows() < requiredRows) {
    sheet.insertRowsAfter(
      sheet.getMaxRows(),
      requiredRows - sheet.getMaxRows()
    );
  }

  if (sheet.getMaxColumns() < requiredColumns) {
    sheet.insertColumnsAfter(
      sheet.getMaxColumns(),
      requiredColumns - sheet.getMaxColumns()
    );
  }

  const dataRange = sheet.getDataRange();
  if (dataRange.getNumRows() > 0 && dataRange.getNumColumns() > 0) {
    dataRange.clearContent();
  }

  sheet
    .getRange(1, 1, 1, headers.length)
    .setValues([headers.slice()]);

  if (rows.length > 0) {
    const values = rows.map(row =>
      headers.map(header =>
        Object.prototype.hasOwnProperty.call(row, header)
          ? row[header]
          : ''
      )
    );

    sheet
      .getRange(2, 1, values.length, headers.length)
      .setValues(values);
  }

  sheet.setFrozenRows(1);
}

function miniAppFindSheet_(spreadsheet, candidateNames, required) {
  for (let i = 0; i < candidateNames.length; i += 1) {
    const sheet = spreadsheet.getSheetByName(candidateNames[i]);
    if (sheet) return sheet;
  }

  if (!required) return null;

  throw new Error(
    'Не найден лист. Проверены названия: ' + candidateNames.join(', ')
  );
}

function miniAppReadSheetObjects_(sheet) {
  const range = sheet.getDataRange();
  const values = range.getValues();

  if (!values || values.length < 2) return [];

  const headers = values[0].map(value => String(value || '').trim());
  const nonEmptyHeaders = headers.filter(Boolean);

  if (nonEmptyHeaders.length === 0) {
    throw new Error('На листе «' + sheet.getName() + '» пустая строка заголовков.');
  }

  const seen = {};
  headers.forEach(header => {
    if (!header) return;
    if (seen[header]) {
      throw new Error(
        'На листе «' + sheet.getName() + '» повторяется заголовок «' + header + '».'
      );
    }
    seen[header] = true;
  });

  const timezone = String(MINIAPP_TIMEZONE || '').trim() ||
    sheet.getParent().getSpreadsheetTimeZone();
  const rows = [];

  for (let rowIndex = 1; rowIndex < values.length; rowIndex += 1) {
    const sourceRow = values[rowIndex];
    const row = {};
    let hasData = false;

    headers.forEach((header, columnIndex) => {
      if (!header) return;
      const value = miniAppSerializeCell_(sourceRow[columnIndex], timezone);
      row[header] = value;
      if (miniAppHasValue_(value)) hasData = true;
    });

    if (hasData) rows.push(row);
  }

  return rows;
}

function miniAppSerializeCell_(value, timezone) {
  if (value instanceof Date && !isNaN(value.getTime())) {
    // В Supabase эти поля имеют тип DATE, поэтому время и часовой пояс не отправляем.
    return Utilities.formatDate(value, timezone, 'yyyy-MM-dd');
  }

  if (typeof value === 'string') {
    // Сохраняем внутренние переводы строк в описании, убираем только края.
    const text = value.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trim();

    // Формулы Google Sheets иногда возвращают пустоту как строку с кавычками.
    if (/^(?:""|''|null|none|undefined|nan)$/i.test(text)) return '';
    return text;
  }

  if (value === null || value === undefined) return '';
  return value;
}

function miniAppMapNovelRow_(row, sheetName) {
  const isLegend = String(sheetName).toLowerCase() === 'legend';

  if (!isLegend) {
    return miniAppRemoveEmptyKeys_(row);
  }

  return miniAppRemoveEmptyKeys_({
    NovelID: miniAppPick_(row, ['NovelID', 'Novel Id', 'ID']),
    Slug: miniAppPick_(row, ['MiniAppSlug', 'Slug']),
    NovelShort: miniAppPick_(row, [
      'NovelShort', 'ShortName', 'Short Title', 'Короткое название', 'Короткое имя',
    ]),
    NovelTitleRu: miniAppPick_(row, [
      'NovelTitleRu', 'NovelTitleRU', 'Title RU', 'TitleRU', 'Название RU',
      'Полное название', 'Название',
    ]),
    NovelTitleEn: miniAppPick_(row, [
      'NovelTitleEn', 'NovelTitleEN', 'Title EN', 'TitleEN', 'Название EN',
      'EnglishTitle', 'Английское название',
    ]),
    PostIcons: miniAppPick_(row, ['PostIcons', 'Post Icons', 'Иконки']),
    CoverURL: miniAppPick_(row, [
      'MiniAppCoverURL', 'CoverURL', 'Cover URL', 'Cover', 'Обложка', 'Ссылка на обложку',
    ]),
    Description: miniAppPick_(row, [
      'MiniAppDescription', 'Description', 'Описание', 'Аннотация',
    ]),
    Tags: miniAppPick_(row, ['MiniAppTags', 'Tags', 'Теги']),
    TopDescription: miniAppPick_(row, [
      'MiniAppTopDescription', 'TopDescription', 'Top Description',
    ]),
    BottomDescription: miniAppPick_(row, [
      'MiniAppBottomDescription', 'BottomDescription', 'Bottom Description',
    ]),
    OriginalLanguage: miniAppPick_(row, [
      'OriginalLanguage', 'Original Language', 'Language', 'Язык оригинала',
    ]),
    TotalChapters: miniAppPick_(row, ['TotalChapters', 'Total Chapters', 'Всего глав']),
    TranslatedChapters: miniAppPick_(row, [
      'TranslatedChapters', 'Translated Chapters', 'Переведено глав',
    ]),
    ProgressPercent: miniAppPick_(row, ['Progress %', 'ProgressPercent', 'Progress']),
    Status: miniAppPick_(row, ['Status', 'Статус']),
    AccessModel: miniAppPick_(row, ['AccessModel', 'Access Model']),
    ScheduleMode: miniAppPick_(row, ['ScheduleMode', 'Schedule Mode']),
    EarlyAccessMode: miniAppPick_(row, ['EarlyAccessMode', 'Early Access Mode']),
    SortOrder: miniAppPick_(row, ['MiniAppSortOrder', 'SortOrder', 'Sort Order']),
    IsVisible: miniAppPick_(row, ['MiniAppIsVisible', 'IsVisible', 'Is Visible', 'Visible']),
    AgeRating: miniAppPick_(row, ['AgeRating', 'Age Rating', 'Возрастной рейтинг']),
    HasAdultBadge: miniAppPick_(row, ['HasAdultBadge', '18+', 'Adult']),
    TranslationStatus: miniAppPick_(row, ['TranslationStatus']),
    TranslationStatusLabel: miniAppPick_(row, ['TranslationStatusLabel']),
    TranslationStatusColor: miniAppPick_(row, ['TranslationStatusColor']),
    RelationType: miniAppPick_(row, ['RelationType']),
    RelationIcon: miniAppPick_(row, ['RelationIcon']),
    RelationColor: miniAppPick_(row, ['RelationColor']),
    TagsShort: miniAppPick_(row, ['TagsShort']),
    TagsTooltip: miniAppPick_(row, ['TagsTooltip']),
    AddedDate: miniAppPick_(row, ['AddedDate', 'Added Date', 'Дата добавления']),
    TranslationAuthor: miniAppPick_(row, [
      'TranslationAuthor', 'Translator', 'Переводчик',
    ]),
  });
}

function miniAppMapChapterRow_(row) {
  return miniAppRemoveEmptyKeys_({
    ChapterID: miniAppPick_(row, ['ChapterID', 'ChapterCode', 'chapter_code']),
    NovelID: miniAppPick_(row, ['NovelID', 'Novel Id']),
    ChapterNo: miniAppPick_(row, ['ChapterNo', 'Chapter No', 'Глава']),
    ChapterTitle: miniAppPick_(row, ['ChapterTitle', 'Chapter Title', 'Название главы']),
    Slug: miniAppPick_(row, ['MiniAppSlug', 'Slug']),
    Volume: miniAppPick_(row, ['Volume', 'Том']),
    VolumeNo: miniAppPick_(row, ['VolumeNo', 'Volume No', 'Номер тома']),
    VolumeTitle: miniAppPick_(row, ['VolumeTitle', 'Volume Title', 'Название тома']),
    TranslationDate: miniAppPick_(row, ['TranslationDate', 'Translation Date']),
    ReleaseDate: miniAppPick_(row, ['ReleaseDate', 'Release Date']),
    FreeReleaseDate: miniAppPick_(row, ['FreeReleaseDate', 'Free Release Date']),
    PremiumReleaseDate: miniAppPick_(row, ['PremiumReleaseDate', 'Premium Release Date']),
    TelegraphURL: miniAppPick_(row, [
      'TelegraphURL', 'Telegraph URL', 'Telegra.ph URL', 'PublishedURL',
    ]),
    TelegraphFreeURL: miniAppPick_(row, [
      'TelegraphFreeURL', 'Telegraph Free URL', 'FreeTelegraphURL', 'FreeURL',
    ]),
    TelegraphPremiumURL: miniAppPick_(row, [
      'TelegraphPremiumURL', 'Telegraph Premium URL', 'PremiumTelegraphURL', 'PremiumURL',
    ]),
    TelegraphFreeCode: miniAppPick_(row, ['TelegraphFreeCode', 'Telegraph Free Code']),
    TelegraphPremiumCode: miniAppPick_(row, [
      'TelegraphPremiumCode', 'Telegraph Premium Code',
    ]),
    SourceType: miniAppPick_(row, ['SourceType', 'Source Type']),
    AccessLevel: miniAppPick_(row, ['AccessLevel', 'Access Level', 'MiniAppAccessLevel']),
    IsVisible: miniAppPick_(row, ['MiniAppIsVisible', 'IsVisible', 'Is Visible']),
    SortOrder: miniAppPick_(row, ['MiniAppSortOrder', 'SortOrder', 'Sort Order']),
  });
}

function miniAppMapFoxRow_(row) {
  return miniAppRemoveEmptyKeys_({
    name: miniAppPick_(row, ['name', 'Name', 'Название', 'fox', 'Fox']),
    url: miniAppPick_(row, ['url', 'URL', 'Url', 'Ссылка', 'ImageURL', 'ImageUrl']),
  });
}

function miniAppPick_(row, aliases) {
  for (let i = 0; i < aliases.length; i += 1) {
    const alias = aliases[i];
    if (Object.prototype.hasOwnProperty.call(row, alias) && miniAppHasValue_(row[alias])) {
      return row[alias];
    }
  }

  const normalized = {};
  Object.keys(row).forEach(key => {
    normalized[miniAppNormalizeHeader_(key)] = row[key];
  });

  for (let i = 0; i < aliases.length; i += 1) {
    const normalizedAlias = miniAppNormalizeHeader_(aliases[i]);
    if (
      Object.prototype.hasOwnProperty.call(normalized, normalizedAlias) &&
      miniAppHasValue_(normalized[normalizedAlias])
    ) {
      return normalized[normalizedAlias];
    }
  }

  return '';
}

function miniAppNormalizeHeader_(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[ё]/g, 'е')
    .replace(/[^a-zа-я0-9]+/gi, '');
}

function miniAppRemoveEmptyKeys_(row) {
  const result = {};
  Object.keys(row).forEach(key => {
    const value = row[key];
    if (miniAppHasValue_(value)) result[key] = value;
  });
  return result;
}

function miniAppHasValue_(value) {
  if (value === null || value === undefined) return false;
  if (typeof value !== 'string') return true;

  const text = value.trim();
  if (!text) return false;
  return !/^(?:""|''|null|none|undefined|nan)$/i.test(text);
}

function miniAppValidatePayload_(novels, chapters, fox, novelSheet, chapterSheet, foxSheet) {
  if (novels.length === 0) {
    throw new Error(
      'Не найдено ни одной книги для отправки.\n' +
        'Лист: ' + novelSheet.getName() + '\n' +
        'Проверьте колонки NovelID и NovelShort/Title.'
    );
  }

  if (chapters.length === 0) {
    throw new Error(
      'Не найдено ни одной главы для отправки.\n' +
        'Лист: ' + chapterSheet.getName() + '\n' +
        'Проверьте колонки ChapterID и NovelID.'
    );
  }

  if (foxSheet && fox.length === 0) {
    throw new Error(
      'Лист «' + foxSheet.getName() + '» найден, но ссылки на лисичек не распознаны.\n' +
        'Нужны две колонки: name и url.'
    );
  }
}

function miniAppPostPayload_(config, payload) {
  const endpoint = config.siteUrl + MINIAPP_SYNC.ENDPOINT_PATH;
  const response = UrlFetchApp.fetch(endpoint, {
    method: 'post',
    contentType: 'application/json; charset=utf-8',
    payload: JSON.stringify(payload),
    muteHttpExceptions: true,
    followRedirects: true,
    headers: {
      Accept: 'application/json',
      'X-Sync-Token': config.syncToken,
    },
  });

  const code = response.getResponseCode();
  const body = response.getContentText('UTF-8');
  const contentType = String(
    response.getHeaders()['Content-Type'] || response.getHeaders()['content-type'] || ''
  ).toLowerCase();

  if (code === 404) {
    throw new Error(
      'Сайт вернул HTTP 404.\n\n' +
        'Скрипт обращался к:\n' + endpoint + '\n\n' +
        'Текущая версия сайта должна содержать POST-маршрут /api/sync.\n' +
        'Если в ответе виден HTML страницы «Зефиркины баоцзы», значит на Render ' +
        'развёрнут старый app.py или в настройках указан неправильный домен.\n\n' +
        miniAppShortText_(body)
    );
  }

  if (code === 403) {
    throw new Error(
      'Сайт вернул HTTP 403: неверный SYNC_TOKEN.\n' +
        'Значение в Apps Script должно полностью совпадать с Render → Environment → SYNC_TOKEN.\n\n' +
        miniAppShortText_(body)
    );
  }

  if (code < 200 || code >= 300) {
    throw new Error(
      'Сайт вернул ошибку HTTP ' + code + '.\n' +
        'Endpoint: ' + endpoint + '\n\n' +
        miniAppShortText_(body)
    );
  }

  if (contentType.indexOf('application/json') === -1 && /^\s*</.test(body)) {
    throw new Error(
      'Сайт вернул HTML вместо JSON.\n' +
        'Проверьте, что используется endpoint ' + endpoint + '.\n\n' +
        miniAppShortText_(body)
    );
  }

  const data = miniAppParseJson_(body, 'Сайт вернул некорректный JSON.');

  if (data.status !== 'ok') {
    throw new Error('Сайт не подтвердил синхронизацию:\n' + miniAppShortText_(body));
  }

  return data;
}

function miniAppParseJson_(text, errorPrefix) {
  try {
    return JSON.parse(String(text || ''));
  } catch (error) {
    throw new Error(errorPrefix + '\n' + miniAppShortText_(text));
  }
}

function miniAppShortText_(text) {
  const value = String(text || '').trim();
  if (value.length <= MINIAPP_SYNC.MAX_RESPONSE_TEXT) return value;
  return value.slice(0, MINIAPP_SYNC.MAX_RESPONSE_TEXT) + '…';
}

function miniAppResultCount_(result, key, fallback) {
  return Object.prototype.hasOwnProperty.call(result, key) ? result[key] : fallback;
}
