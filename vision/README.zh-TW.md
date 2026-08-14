# crywatch-vision 👀

[English](README.md) | 繁體中文

**教你的嬰兒監視器「看得懂」——訓練一個屬於你自己的偵測模型，判斷寶寶到底在不在床上**，就算是夜視灰階、就算整個包在被子裡只露一隻腳。

這是 [crywatch](../README.zh-TW.md) 的**選配「視覺」模組**。crywatch 主專案教它「聽」——分得出真的哭聲還是只是很吵；這個模組教它「看」：盯著嬰兒床鏡頭，太久沒偵測到寶寶就推播（離開床／被蓋住？），偵測到動作就提示（睡醒／翻身／爬動），並在網頁看板的畫面上疊一個即時紅框。

> ⚠️ **本模組不附任何模型、也不附任何影像。** 用寶寶訓練出來的模型屬於隱私資料。你要用**自己的**相機畫面訓練**自己的**模型。這裡給你的是「一個週末就能自己做出來」的**整套流程與工具**——沒有任何人的真實寶寶資料被公開；而且你的 `frames/`、`labels/`、`*.pt` 都被 gitignore 擋著，不會外流。

---

## 為什麼一定要「訓練自己的」

最直覺的第一步是：拿現成的偵測模型（YOLO）對著嬰兒床。白天很好用，一到晚上就崩——夜視灰階＋被子包住的寶寶，模型信心掉到約 0.03，等於「我根本看不到寶寶」。現成模型是拿「白天、清楚、站著的成年人」訓練的，它沒看過「你家夜視鏡頭下、裹在被子裡的嬰兒」。

所以這裡的偵測器不是什麼神奇的預訓練模型，而是一個**迴路**，讓你專門教它一直答錯的那些畫面：

```
 收集影格 ──► 偵測器自動存下「它漏抓的畫面」(frames/hard/)
      ▲                          │
      │                          ▼
   重新訓練 ◄── 你驗證 ◄── AI 先幫你把框畫好 (prelabel.py)
  (借一張 GPU)  (labeling/)
```

這就是**資料飛輪（data flywheel）**：不是亂餵幾千張，而是專餵它自己的死角。每一輪很小（約 100 張），但進步很大。作者自己的實測：難姿勢的抓到率（recall）在兩個短短的迴圈裡，大約從**十張抓兩張 → 十張抓九張以上**；而且第二輪只需要約 120 張，因為模型已經幫忙把一半的框預先畫好讓你驗證。

---

## 目錄長什麼樣

```
vision/
├── detector/            # 服務：抓 go2rtc 快照 → 偵測 → 在/不在/動作 → ntfy + 疊框
├── labeling/            # 瀏覽器標註工具（含 AI 建議框）+ 收集影格
├── training/            # AI 預標 + 微調 yolo11s → baby.pt + 遠端 Docker 訓練
├── .env.example
└── requirements.txt
```

全部用環境變數設定（見 `.env.example`）。偵測器 CPU/GPU 都能跑；訓練需要 GPU（便宜的就夠，模型很小）。

---

## 流程（大約一個週末）

**0. 前置。** 一個能動的 [go2rtc](https://github.com/AlexxIT/go2rtc)（相機串流）＋一個 [ntfy](https://ntfy.sh) 推播 topic。`pip install -r requirements.txt`。

**1. 收第一批資料。**
```bash
cd vision/labeling
CAMS=cam2=bedroom python3 collect_frames.py --interval 30
```

**2. 標註（快，AI 輔助）。** 先用手上的模型（第一輪用現成 `yolo11s.pt`）把框預先畫好，你只驗證：
```bash
cd ../training && python3 prelabel.py --model yolo11s.pt
cd ../labeling && FRAMES_DIR=frames/review python3 label_server.py
# 開 http://localhost:1987/ → 橘色虛線=AI 猜的：對就存、要修就拉、完全錯就重畫。空床按「no baby」。
```

**3. 在「另一張 GPU」上訓練。** 別用驅動你桌面的那張卡（一訓練畫面會凍住 😅）：
```bash
rsync -a frames/ labels/ ../training/train_baby.py  TRAIN_HOST:~/baby-train/
ssh TRAIN_HOST 'cd ~/baby-train && bash remote_train.sh'
scp TRAIN_HOST:~/baby-train/baby.pt ../detector/baby.pt
```

**4. 部署。**
```bash
cd ../detector && cp ../.env.example .env    # 設 STREAM、NTFY_URL、MODEL=./baby.pt…
python3 presence_detector.py
```

**5. 讓它自我進化。** `HARD_COLLECT=1` 時，偵測器會把「漏抓、但寶寶其實在」的畫面存進 `frames/hard/`。過幾晚拿這些重跑 2–4 步——這就是飛輪，每一輪都更準。

---

## 幾個值得知道的功能

- **睡覺區。** 用看板的 ✏️ 把整張床框一次（`/zone/set`）。之後框內接受較弱偵測、且「有動作」只算床內（大人走過不算）。是最後那幾張「全遮全靜」極限畫面的保險。
- **布防開關 + 偵測不到警報開關。** 一個小小的 HTTP 控制 API（`/arm`、`/disarm`、`/absent/off`、`/zone/set`…），看板把它接成按鈕——白天空床時就不會一直吵。
- **一個寶寶一個框。** 疊圖只顯示信心最高那一框，不會「一個寶寶兩個紅框」。
- **全本地、不上雲。** 快照來自你自己的 go2rtc、通知進你自己的 ntfy，寶寶資料不出家門。

## 授權

Apache-2.0，跟 crywatch 一致（見 [../LICENSE](../LICENSE)）。訓練/推論會用到 [Ultralytics YOLO11](https://github.com/ultralytics/ultralytics)（**AGPL-3.0**）——商用前請先看它的授權。
