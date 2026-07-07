# zenn-bot / 鍙屽钩鍙拌嚜鍔ㄥ寲鍙戝竷绯荤粺

鍩轰簬鍚屼竴浠介涔︿富棰樻睜锛屽疄鐜帮細

- Zenn 鑷姩鐢熸垚鏂囩珷骞堕€氳繃 GitHub 鑷姩閮ㄧ讲
- Hatenablog 鑷姩鐢熸垚鏂囩珷骞堕€氳繃 AtomPub API 鐩村彂
- 缁熶竴鐘舵€佺鐞嗐€侀涔﹀洖鍐欏拰缇よ亰閫氱煡

---

## 涓€銆侀」鐩畾浣?

杩欐槸涓€涓繍琛屽湪 Windows 鏈湴鐨勮嚜鍔ㄥ寲鍙戝竷椤圭洰锛屽綋鍓嶇洰鏍囨槸绋冲畾缁存姢鐜版湁鍙敤閾捐矾锛岃€屼笉鏄噸鍋氱郴缁熴€?

褰撳墠宸茶窇閫氾細

- Zenn 鑷姩鍙戝竷
- Hatenablog 鑷姩鍙戝竷
- 椋炰功缁熶竴绠＄悊涓婚姹?
- 鏂囩珷鐢熸垚銆佺姸鎬佸洖鍐欍€佺兢鑱婇€氱煡
- Zenn 鏈湴閰嶉淇濇姢

---

## 浜屻€侀」鐩洰褰?

鏈湴椤圭洰鐩綍锛?

`E:\yanque\娴峰鎶曟斁\zenn-bot`

Zenn 浠撳簱鐩綍锛?

`E:\yanque\娴峰鎶曟斁\zen\takkenai-zenn`

甯哥敤鍏抽敭鏂囦欢锛?

- `main.py`
- `feishu_client.py`
- `generator.py`
- `image_manager.py`
- `link_inserter.py`
- `retry_manager.py`
- `publish_gate.py`
- `git_publisher.py`
- `zenn_writer.py`
- `hatena_writer.py`
- `hatena_client.py`
- `hatena_publisher.py`
- `bot_notifier.py`
- `run_publish.bat`
- `.env`

鏃ュ織鐩綍锛?

- `logs/`

Zenn 閰嶉鎺у埗鏂囦欢锛?

- `publish_control.json`

---

## 涓夈€佸彂甯冮摼璺?

### 1. Zenn

澶勭悊閫昏緫锛?

1. 浠庨涔﹁鍙?`platform=zenn` 鐨勮褰?
2. 鏍规嵁 `publish_date <= 浠婂ぉ` 涓旂姸鎬佷负 `ready / queued / waiting` 杩涜澶勭悊
3. 璋冪敤 Moonshot / Kimi 鐢熸垚鏃ユ枃 Markdown 姝ｆ枃
4. 鍐欏叆 Zenn 浠撳簱 `articles/*.md`
5. 鎵ц git commit / push
6. 瑙﹀彂 Zenn 鐨?GitHub 鑷姩閮ㄧ讲
7. 鍥炲啓椋炰功瀛楁
8. 鍙戦€侀涔﹂兢鑱婇€氱煡

### 2. Hatenablog

澶勭悊閫昏緫锛?

1. 浠庨涔﹁鍙?`platform=hatenablog` 鐨勮褰?
2. 鏍规嵁 `publish_date <= 浠婂ぉ` 涓旂姸鎬佷负 `ready` 鐨勮褰曡繘琛屽鐞?
3. 璋冪敤 Moonshot / Kimi 鐢熸垚鏃ユ枃 Markdown 姝ｆ枃
4. 閫氳繃 Hatena AtomPub API 鐩村彂
5. 鍥炲啓椋炰功瀛楁
6. 鍙戦€侀涔﹂兢鑱婇€氱煡

---

## 鍥涖€侀涔︿富棰樻睜瀛楁

### 鎵嬪伐缁存姢瀛楁

- `topic`
- `keywords`
- `brief`
- `platform`
- `publish_date`
- `status`
- `slug`
- `emoji`
- `image_prompt`
- `anchor_links`

> 璇存槑锛歚anchor_links` 瀛楁褰撳墠鍙互缁х画淇濈暀鍦ㄩ涔﹁〃涓紝浣嗚繍琛屾湡姝ｆ枃鎻掗摼宸叉敼涓轰紭鍏堜緷鎹?`keywords` 澶勭悊銆?

### 绋嬪簭鍥炲啓瀛楁

- `article_title`
- `article_excerpt`
- `article_path`
- `article_url`
- `edit_url`
- `platform_post_id`
- `published_at`
- `last_push_at`
- `last_result`
- `retry_count`
- `error_message`

---

## 浜斻€佺姸鎬佹祦杞?

### Zenn

- `ready`锛氶娆＄敓鎴愭枃绔犲苟灏濊瘯鍙戝竷
- `queued`锛氭枃绔犲凡鐢熸垚锛屼絾鍥犱负閰嶉淇濇姢鏈?push
- `waiting`锛氬凡 push GitHub锛岀瓑寰?Zenn 鏈€缁堢‘璁ゆ垨鍚庣画 retry
- `published`锛氫汉宸ョ‘璁ゅ悗鏀?
- `failed`锛氬け璐?

### Hatenablog

- `ready`锛氱敓鎴愭枃绔犲苟鐩存帴 API 鍙戞枃
- `published`锛氬彂甯冩垚鍔?
- `failed`锛氬け璐?

---

## 鍏€佸綋鍓嶇敓鎴愯鍒?

褰撳墠 `generator.py` 鐨勬牳蹇冩€濊矾锛?

- 妯″瀷鍙礋璐ｈ緭鍑哄畬鏁存棩鏂?Markdown 姝ｆ枃
- 鏈湴浠ｇ爜璐熻矗缁勮鏍囬銆佹憳瑕併€乼opics 绛夊厓淇℃伅
- 涓嶅啀瑕佹眰妯″瀷杩斿洖 JSON
- 瀵圭敓鎴愮粨鏋滆繘琛岃川閲忔鏌ワ紝閬垮厤鍙戝竷鎻愮翰鏂囥€佹ā鏉挎枃銆佸崰浣嶆枃

### 褰撳墠璐ㄩ噺瑕佹眰

鍙€氳繃鐜鍙橀噺璋冩暣锛岄粯璁ゅ缓璁細

- `ARTICLE_MIN_BODY_CHARS=1200`
- `ARTICLE_MIN_BODY_CHARS_ZENN=1400`
- `ARTICLE_MIN_BODY_CHARS_HATENA=900`
- `ARTICLE_MAX_TOKENS=3200`

### 褰撳墠姝ｆ枃鎻掗摼瑙勫垯

- 浼樺厛渚濇嵁 `keywords` 鍋氶椤甸摼鎺ユ彃鍏?
- 棣栭〉鍦板潃榛樿锛歚https://www.takkenai.jp/`
- 鑻ユ鏂囪嚜鐒跺嚭鐜?`涓嶅嫊鐢I` 鎴?`TakkenAI`锛屽厑璁哥粰鍝佺墝璇嶅姞棣栭〉閾炬帴
- 涓嶅己鍒跺搧鐗屾鍏ワ紝閬垮厤鏂囩珷鐢熺‖
- 姣忕瘒鏂囩珷寤鸿鎺у埗鍏抽敭璇嶉摼鎺ユ暟閲忥紝榛樿涓嶅疁杩囧

### 褰撳墠璐ㄩ噺澶辫触閲嶈瘯瑙勫垯

- 濡傛灉姝ｆ枃璐ㄩ噺涓嶈冻锛屼笉绔嬪嵆褰诲簳澶辫触
- 闂撮殧 1 灏忔椂鍚庡啀娆￠噸璇?
- 鏈€澶氶噸璇?3 娆?
- 瓒呰繃 3 娆″悗鐘舵€佸啓涓?`failed`

---

## 涓冦€乑enn 閰嶉淇濇姢

鐩殑锛?

閬垮厤鎾炰笂 Zenn 鎻愪氦 / 閮ㄧ讲鏁伴噺闄愬埗銆?

褰撳墠瑙勫垯锛?

- 姣忓ぉ鎬?push 涓婇檺锛?
- 姣忓ぉ鏂板彂涓婇檺锛?
- `waiting` retry 鍐峰嵈锛?4 灏忔椂
- 姣忎釜 slug 姣忓ぉ鏈€澶?retry锛? 娆?

---

## 鍏€佽繍琛屾柟寮?

### 1. 鎵嬪姩杩愯

鍦ㄩ」鐩牴鐩綍鎵ц锛?

```bat
python main.py
