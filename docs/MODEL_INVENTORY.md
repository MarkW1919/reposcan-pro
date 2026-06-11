# MODEL_INVENTORY.md

> **Generated** by `scripts/inventory_trained_models.py` — do not edit by hand.
> Last generated: `2026-06-11T18:31:28Z`

Weights are gitignored (no_model_weight_commits); this catalog is the tracked record. Restore weights from backup and verify with --verify against the recorded sha256.

**103 real trained weights** (106 artifacts incl. fixtures), total 2584.9 MB.

To verify integrity / detect loss after a clone or restore:

```
python scripts/inventory_trained_models.py --verify
```

## Trained runs (accuracy where recorded)

| Run | Holdout | Val | Notes |
|---|---:|---:|---|
| `lpr_ocr_openalpr_support_continue_20260503_0002` | — | — | openalpr-us-benchmark |
| `open_images_make_model_reviewed_seed_cpu_20260416` | 0.0000 | 0.2000 |  |
| `open_images_make_model_reviewed_seed_cpu_20260416_r2` | 0.0000 | 0.2000 |  |
| `open_images_make_model_reviewed_seed_cpu_20260417` | 0.1111 | 0.2500 |  |
| `open_images_vehicle_color_reviewed_seed_20260417` | 0.0000 | 0.1000 |  |
| `vehicle-color-canonical-v1_20260512_run1` | — | 0.9879 |  |
| `vehicle-make-model-canonical-v1_20260506_run1` | 0.9647 | 0.9640 |  |
| `vehicle-make-model-canonical-v2_20260507_run1` | 0.9473 | 0.9570 |  |
| `vehicle-make-model-canonical-v3_20260508_run1` | 0.8763 | 0.9211 |  |
| `vehicle-make-model-canonical-v4_20260510_run1` | 0.8922 | 0.9165 |  |
| `vehicle-make-model-canonical-v5_20260519_run1` | 0.8633 | 0.8964 |  |
| `vehicle-make-model-warmstart-v2_20260409_141756` | 0.8493 | 0.8534 |  |
| `vehicle-rerank-gm-fullsize-suv-v1_20260512_run1` | 0.8382 | 0.8833 |  |
| `vehicle-rerank-jeep-realonly-v1_20260514_run1` | 0.9375 | 0.9375 |  |
| `vehicle-rerank-jeep-v1_20260512_run1` | 0.6250 | 0.8750 |  |
| `vehicle-rerank-tall-suv-v2_20260602_run1` | 0.7738 | 0.8158 |  |
| `vehicle-year-bucket-canonical-v1_20260509_run1` | 0.6773 | 0.6980 |  |
| `vehicle_detector_open_images_cpu_smoke_20260415` | — | — |  |
| `vehicle_detector_open_images_cpu_smoke_20260428_autonomy1` | — | — |  |
| `vehicle_detector_open_images_cpu_smoke_20260428_ui_fix` | — | — |  |
| `vehicle_detector_open_images_cpu_smoke_3000_20260415` | — | — |  |
| `vehicle_make_model_warmstart_20260331_rerun2` | — | — |  |
| `vehicle_make_model_warmstart_20260403_visible_rerun1` | — | — |  |
| `vehicle_make_model_warmstart_cpu_20260401_rerun1` | — | — |  |
| `vehicle_make_model_warmstart_cpu_20260402_continue1` | — | — |  |
| `vehicle_make_model_warmstart_cpu_20260427` | 0.6931 | 0.7015 |  |
| `vehicle_make_model_warmstart_regularized_20260407_rerun1` | 0.8444 | 0.8452 |  |
| `vehicle_make_model_warmstart_v3_palette_continue_20260430_01` | — | — |  |
| `vehicle_make_model_warmstart_v3_polish_20260427` | 0.8560 | 0.8567 |  |
| `vehicle_make_model_warmstart_v3_polish_continue_20260430_01` | 0.8595 | 0.8649 |  |
| `vehicle_make_model_warmstart_v3_polish_continue_20260503_0002` | 0.8582 | 0.8632 |  |

## Artifacts (SHA-256 truncated to 16 chars)

| Path | Size | SHA-256 | Modified |
|---|---:|---|---|
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/best_accuracy.pdparams` | 65.5 MB | `74e78e6650072df7` | 2026-05-03T09:54:04Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/best_model/model.pdparams` | 65.5 MB | `74e78e6650072df7` | 2026-05-03T09:54:04Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_72.pdparams` | 65.5 MB | `784824b33429c4f1` | 2026-05-03T05:55:43Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_73.pdparams` | 65.5 MB | `8a31ef192284a054` | 2026-05-03T06:30:08Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_74.pdparams` | 65.5 MB | `6da0379e64e409c6` | 2026-05-03T07:03:46Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_75.pdparams` | 65.5 MB | `78320af7876f235c` | 2026-05-03T07:36:27Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_76.pdparams` | 65.5 MB | `a6f5d278e71cca92` | 2026-05-03T08:09:25Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_77.pdparams` | 65.5 MB | `1265ab9fdd805725` | 2026-05-03T08:42:48Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_78.pdparams` | 65.5 MB | `5f0fc66965b9f9b2` | 2026-05-03T09:15:39Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_79.pdparams` | 65.5 MB | `97de3f696200acf4` | 2026-05-03T09:47:44Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/iter_epoch_80.pdparams` | 65.5 MB | `8776e5d5af618e23` | 2026-05-03T10:19:55Z |
| `runtime/training/lpr_ocr_openalpr_support_continue_20260503_0002/output/latest.pdparams` | 65.5 MB | `8776e5d5af618e23` | 2026-05-03T10:19:55Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260416/checkpoints/best.pt` | 42.7 MB | `52ca02ba9e308fcc` | 2026-04-17T04:21:22Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260416/checkpoints/last.pt` | 42.7 MB | `8aab47345ce86b42` | 2026-04-17T04:21:30Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260416/exports/model.onnx` | 42.6 MB | `97eb4814adfad2d0` | 2026-04-17T04:21:31Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260416_r2/checkpoints/best.pt` | 42.7 MB | `2ace77dbf169f57f` | 2026-04-17T04:25:54Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260416_r2/checkpoints/last.pt` | 42.7 MB | `d9c8107d82befdc5` | 2026-04-17T04:25:54Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260416_r2/exports/model.onnx` | 42.6 MB | `24c17d5c3b876e9f` | 2026-04-17T04:25:54Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260417/checkpoints/best.pt` | 42.7 MB | `7a56ac3e071015f7` | 2026-04-17T17:27:07Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260417/checkpoints/last.pt` | 42.7 MB | `34ebf7f2f0b62e9a` | 2026-04-17T17:27:17Z |
| `runtime/training/open_images_make_model_reviewed_seed_cpu_20260417/exports/model.onnx` | 42.6 MB | `8a16d15cfe88da53` | 2026-04-17T17:27:18Z |
| `runtime/training/open_images_vehicle_color_reviewed_seed_20260417/checkpoints/best.pt` | 15.6 MB | `f10ec98cf692aedb` | 2026-04-17T17:30:23Z |
| `runtime/training/open_images_vehicle_color_reviewed_seed_20260417/checkpoints/last.pt` | 15.6 MB | `9fe10bd25f81a583` | 2026-04-17T17:30:57Z |
| `runtime/training/open_images_vehicle_color_reviewed_seed_20260417/exports/model.onnx` | 15.3 MB | `88fb8bdcb0a838f7` | 2026-04-17T17:30:58Z |
| `runtime/training/vehicle-color-canonical-v1_20260512_run1/checkpoints/best.pt` | 15.6 MB | `587d44941e108fdc` | 2026-05-14T12:30:57Z |
| `runtime/training/vehicle-color-canonical-v1_20260512_run1/checkpoints/last.pt` | 15.6 MB | `6583abdf396f81b2` | 2026-05-14T12:48:58Z |
| `runtime/training/vehicle-color-canonical-v1_20260512_run1/exports/model.onnx` | 15.3 MB | `c557ca77a49ab393` | 2026-05-14T12:49:00Z |
| `runtime/training/vehicle-make-model-canonical-v1_20260506_run1/checkpoints/best.pt` | 15.6 MB | `198e57da5992343d` | 2026-05-06T22:26:08Z |
| `runtime/training/vehicle-make-model-canonical-v1_20260506_run1/checkpoints/last.pt` | 15.6 MB | `2bca4aa100c04c08` | 2026-05-07T00:00:43Z |
| `runtime/training/vehicle-make-model-canonical-v1_20260506_run1/exports/model.onnx` | 15.4 MB | `9a834c3ec95df140` | 2026-05-07T00:00:53Z |
| `runtime/training/vehicle-make-model-canonical-v2_20260507_run1/checkpoints/best.pt` | 15.6 MB | `b5717bb410184f63` | 2026-05-07T18:11:36Z |
| `runtime/training/vehicle-make-model-canonical-v2_20260507_run1/checkpoints/last.pt` | 15.6 MB | `956a6466eb428b76` | 2026-05-07T19:52:21Z |
| `runtime/training/vehicle-make-model-canonical-v2_20260507_run1/exports/model.onnx` | 15.4 MB | `d7b2ebcc07b3769a` | 2026-05-07T19:52:28Z |
| `runtime/training/vehicle-make-model-canonical-v3_20260508_run1/checkpoints/best.pt` | 15.7 MB | `bd10f11e091c6ab7` | 2026-05-09T05:50:52Z |
| `runtime/training/vehicle-make-model-canonical-v3_20260508_run1/checkpoints/last.pt` | 15.7 MB | `bd08c51cd4e77a45` | 2026-05-09T08:21:23Z |
| `runtime/training/vehicle-make-model-canonical-v3_20260508_run1/exports/model.onnx` | 15.4 MB | `2e020d4e88f5e35d` | 2026-05-09T08:21:29Z |
| `runtime/training/vehicle-make-model-canonical-v4_20260510_run1/checkpoints/best.pt` | 15.7 MB | `cf05c78964198b3d` | 2026-05-11T18:15:22Z |
| `runtime/training/vehicle-make-model-canonical-v4_20260510_run1/checkpoints/last.pt` | 15.7 MB | `d7b353df946704b5` | 2026-05-11T19:40:24Z |
| `runtime/training/vehicle-make-model-canonical-v4_20260510_run1/exports/model.onnx` | 15.4 MB | `740073097d0d625f` | 2026-05-11T19:40:27Z |
| `runtime/training/vehicle-make-model-canonical-v5_20260519_run1/checkpoints/best.pt` | 15.7 MB | `35227db57f21f443` | 2026-05-20T20:34:46Z |
| `runtime/training/vehicle-make-model-canonical-v5_20260519_run1/checkpoints/last.pt` | 15.7 MB | `93a074d9bf67ab81` | 2026-05-21T00:38:23Z |
| `runtime/training/vehicle-make-model-canonical-v5_20260519_run1/exports/model.onnx` | 15.5 MB | `58e181cb6009c4cb` | 2026-05-21T00:38:25Z |
| `runtime/training/vehicle-make-model-warmstart-v2_20260409_141756/checkpoints/best.pt` | 16.5 MB | `4b4cdac4ca9307da` | 2026-04-14T08:06:00Z |
| `runtime/training/vehicle-make-model-warmstart-v2_20260409_141756/checkpoints/last.pt` | 16.5 MB | `d66b80a8157ae716` | 2026-04-14T08:06:00Z |
| `runtime/training/vehicle-make-model-warmstart-v2_20260409_141756/exports/model.onnx` | 16.2 MB | `64b9cc2bb3c60570` | 2026-04-14T08:06:02Z |
| `runtime/training/vehicle-rerank-gm-fullsize-suv-v1_20260512_run1/checkpoints/best.pt` | 15.6 MB | `a9ae8c87a2bb15d7` | 2026-05-14T15:11:15Z |
| `runtime/training/vehicle-rerank-gm-fullsize-suv-v1_20260512_run1/checkpoints/last.pt` | 15.6 MB | `ad7d1bd89e5e4fd6` | 2026-05-14T15:16:33Z |
| `runtime/training/vehicle-rerank-gm-fullsize-suv-v1_20260512_run1/exports/model.onnx` | 15.3 MB | `8deec5ba199857b9` | 2026-05-14T15:16:35Z |
| `runtime/training/vehicle-rerank-jeep-realonly-v1_20260514_run1/checkpoints/best.pt` | 15.6 MB | `b64ebd43ae812fe2` | 2026-05-14T18:43:31Z |
| `runtime/training/vehicle-rerank-jeep-realonly-v1_20260514_run1/checkpoints/last.pt` | 15.6 MB | `c8e3fc95ca6db4cd` | 2026-05-14T18:45:58Z |
| `runtime/training/vehicle-rerank-jeep-realonly-v1_20260514_run1/exports/model.onnx` | 15.3 MB | `a92c07bc69288c4e` | 2026-05-14T18:46:00Z |
| `runtime/training/vehicle-rerank-jeep-v1_20260512_run1/checkpoints/best.pt` | 15.6 MB | `5e3909b182dfe9f4` | 2026-05-14T13:38:13Z |
| `runtime/training/vehicle-rerank-jeep-v1_20260512_run1/checkpoints/last.pt` | 15.6 MB | `56d17333f8ff5935` | 2026-05-14T14:58:45Z |
| `runtime/training/vehicle-rerank-jeep-v1_20260512_run1/exports/model.onnx` | 15.3 MB | `48869dbc527ec38f` | 2026-05-14T14:59:10Z |
| `runtime/training/vehicle-rerank-tall-suv-v2_20260602_run1/checkpoints/best.pt` | 15.6 MB | `a0dbbe156fde7c8a` | 2026-06-03T00:44:43Z |
| `runtime/training/vehicle-rerank-tall-suv-v2_20260602_run1/checkpoints/last.pt` | 15.6 MB | `43954ca6bcc3fc0e` | 2026-06-03T00:59:16Z |
| `runtime/training/vehicle-rerank-tall-suv-v2_20260602_run1/exports/model.onnx` | 15.3 MB | `d3d9362d6643c5df` | 2026-06-03T00:59:18Z |
| `runtime/training/vehicle-year-bucket-canonical-v1_20260509_run1/checkpoints/best.pt` | 15.6 MB | `995b664a5be83e55` | 2026-05-10T01:56:14Z |
| `runtime/training/vehicle-year-bucket-canonical-v1_20260509_run1/checkpoints/last.pt` | 15.6 MB | `790ae898b5d01456` | 2026-05-10T02:50:21Z |
| `runtime/training/vehicle-year-bucket-canonical-v1_20260509_run1/exports/model.onnx` | 15.3 MB | `368415ea98a57585` | 2026-05-10T02:50:23Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260415/promoted-bundle/artifacts/best.onnx` | 9.9 MB | `020fa2f2a056d629` | 2026-04-15T17:38:34Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260415/weights/best.onnx` | 9.9 MB | `020fa2f2a056d629` | 2026-04-15T17:38:34Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260415/weights/best.pt` | 5.2 MB | `81f50425d1483271` | 2026-04-15T17:38:30Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260415/weights/last.pt` | 5.2 MB | `40f7377f2d4ca9f4` | 2026-04-15T17:38:30Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260428_autonomy1/weights/best.onnx` | 9.9 MB | `075a30b2413a134f` | 2026-04-28T19:41:56Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260428_autonomy1/weights/best.pt` | 5.2 MB | `155b418a000b1ab8` | 2026-04-28T19:41:45Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260428_autonomy1/weights/last.pt` | 5.2 MB | `4593dba80dca2500` | 2026-04-28T19:41:45Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260428_ui_fix/weights/best.onnx` | 9.9 MB | `f24cb6ece39263d6` | 2026-04-28T23:41:21Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260428_ui_fix/weights/best.pt` | 5.2 MB | `9cc83c9f8ad4eab7` | 2026-04-28T23:41:10Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_20260428_ui_fix/weights/last.pt` | 5.2 MB | `acf14afa139b92bb` | 2026-04-28T23:41:10Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_3000_20260415/weights/best.onnx` | 9.9 MB | `dc0644dd432475ad` | 2026-04-15T18:41:07Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_3000_20260415/weights/best.pt` | 5.2 MB | `cc2d4abe95632b7c` | 2026-04-15T18:40:55Z |
| `runtime/training/vehicle_detector_open_images_cpu_smoke_3000_20260415/weights/last.pt` | 5.2 MB | `096c1b10f8a0bc2a` | 2026-04-15T18:40:55Z |
| `runtime/training/vehicle_make_model_warmstart_20260331_rerun2/checkpoints/best.pt` | 16.5 MB | `531de72cb6465422` | 2026-04-01T06:50:16Z |
| `runtime/training/vehicle_make_model_warmstart_20260403_visible_rerun1/checkpoints/best.pt` | 16.5 MB | `3dbd2d5306539861` | 2026-04-04T18:14:29Z |
| `runtime/training/vehicle_make_model_warmstart_20260403_visible_rerun1/checkpoints/last.pt` | 16.5 MB | `902a2fcc37c36d3b` | 2026-04-06T23:43:21Z |
| `runtime/training/vehicle_make_model_warmstart_20260403_visible_rerun1/exports/model.onnx` | 16.2 MB | `93efedef5b2213c8` | 2026-04-06T23:43:25Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260401_rerun1/checkpoints/best.pt` | 43.1 MB | `d53e96932baea2ca` | 2026-04-01T15:57:22Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260401_rerun1/checkpoints/last.pt` | 43.1 MB | `cce15faab27c4650` | 2026-04-01T15:57:22Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260401_rerun1/exports/model.onnx` | 43.0 MB | `fa120c1d981f3a6b` | 2026-04-01T21:42:28Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260402_continue1/checkpoints/best.pt` | 43.1 MB | `60e9821acf177637` | 2026-04-03T04:58:49Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260402_continue1/checkpoints/last.pt` | 43.1 MB | `e3acc374341a2fee` | 2026-04-03T05:07:26Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260402_continue1/exports/model.onnx` | 43.0 MB | `e3fe70414c0cba1b` | 2026-04-03T05:07:30Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260427/checkpoints/best.pt` | 43.1 MB | `2fef79f17f578a37` | 2026-04-27T16:56:58Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260427/checkpoints/last.pt` | 43.1 MB | `ed596709889fe930` | 2026-04-27T17:11:12Z |
| `runtime/training/vehicle_make_model_warmstart_cpu_20260427/exports/model.onnx` | 43.0 MB | `76d00345f8aa994c` | 2026-04-27T17:11:13Z |
| `runtime/training/vehicle_make_model_warmstart_regularized_20260407_rerun1/checkpoints/best.pt` | 16.5 MB | `e1371f0cdf26b906` | 2026-04-08T03:17:38Z |
| `runtime/training/vehicle_make_model_warmstart_regularized_20260407_rerun1/checkpoints/last.pt` | 16.5 MB | `feb70ff0971008a3` | 2026-04-09T09:09:46Z |
| `runtime/training/vehicle_make_model_warmstart_regularized_20260407_rerun1/exports/model.onnx` | 16.2 MB | `619e08c3460d50be` | 2026-04-11T04:56:12Z |
| `runtime/training/vehicle_make_model_warmstart_v3_palette_continue_20260430_01/checkpoints/best.pt` | 16.5 MB | `6e6b6c4e9c81395c` | 2026-04-30T17:00:54Z |
| `runtime/training/vehicle_make_model_warmstart_v3_palette_continue_20260430_01/checkpoints/last.pt` | 16.5 MB | `22c114b635f17f4b` | 2026-04-30T17:00:54Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_20260427/checkpoints/best.pt` | 16.5 MB | `2c240a4ece544bc3` | 2026-04-27T21:49:22Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_20260427/checkpoints/last.pt` | 16.5 MB | `c04ece594cd2c0cc` | 2026-04-28T00:28:22Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_20260427/exports/model.onnx` | 16.2 MB | `2aada34eceb51605` | 2026-04-28T00:28:25Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_continue_20260430_01/checkpoints/best.pt` | 16.5 MB | `9dcb1693a5c7210f` | 2026-04-30T07:46:16Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_continue_20260430_01/checkpoints/last.pt` | 16.5 MB | `404a442fdceeeaa6` | 2026-04-30T10:15:44Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_continue_20260430_01/exports/model.onnx` | 16.2 MB | `3abebd1a3e27e068` | 2026-04-30T10:15:48Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_continue_20260503_0002/checkpoints/best.pt` | 16.5 MB | `a566a752330a50f6` | 2026-05-03T11:15:43Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_continue_20260503_0002/checkpoints/last.pt` | 16.5 MB | `5dc860fae47760e6` | 2026-05-03T13:44:03Z |
| `runtime/training/vehicle_make_model_warmstart_v3_polish_continue_20260503_0002/exports/model.onnx` | 16.2 MB | `f517838bbabd9e7b` | 2026-05-03T13:44:05Z |
| `runtime/models/plate-detector/yolo-v9-t-384-license-plates-end2end.onnx` | 7.4 MB | `888397b96d761c89` | 2026-06-11T18:16:26Z |
| `runtime/models/plate-ocr/cct_xs_v2_global.onnx` | 3.2 MB | `8031afb5fdc6b4d8` | 2026-06-11T18:26:00Z |
| `runtime/models/ultralytics/yolov8s.pt` | 21.5 MB | `1f47a78bf100391c` | 2026-04-19T21:47:42Z |
