---
name: blender-core
description: 에이전트가 수행하는 Blender 5.2+ 작업의 기반. MCP(실시간) 또는 헤드리스 CLI를 통한 bpy 실행, 컨텍스트 오버라이드, 언어 설정에 안전한 노드 검색, 열거형 값 확인, 5.x API 변경, 검증을 다룬다. Blender, bpy, .blend, 3D 에셋 요청에서 먼저 사용하고 전문 blender-* 스킬로 연결한다.
license: MIT
compatibility: Blender 5.2 LTS 이상. 실시간 세션에는 blender-mcp 서버를 선택적으로 사용한다.
metadata:
  author: blender-agent-skills
  version: "1.2.0"
---

<!-- Korean translation of SKILL.md. Source: EL4CTEO/blender-skills @ fb92cfb4cc5a238c22113a6a230b09f535bd0656. Prose translated; executable examples and API identifiers retained. -->

# Blender 기본 스킬 5.2 LTS 이상

## 작업에 맞는 전문 스킬 선택

| 작업 | 스킬 |
|---|---|
| 단위, 컬렉션, 이름 규칙, 링크, 에셋 라이브러리 | `blender-scene-setup` |
| 하드서피스 모델링, 베벨, 불리언, 노멀 | `blender-hardsurface-modeling` |
| 스컬프팅, 멀티레졸루션, 리메시 | `blender-sculpting` |
| 리토폴로지, UV 언랩, 텍셀 밀도 | `blender-retopology-uv` |
| PBR 재질, 색 공간, 텍스처 세트 | `blender-pbr-materials` |
| 마모, 때, 먼지, 데칼, 트림 시트, 텍스처 페인팅 | `blender-texturing` |
| 고해상도→저해상도 맵 베이크: 노멀, AO, 곡률 등 | `blender-texture-baking` |
| 지오메트리 노드, 절차적 모델링 | `blender-geometry-nodes` |
| 바디 리깅, Rigify, 웨이트 페인팅 | `blender-character-rigging` |
| 얼굴 리그, 셰이프 키, ARKit, 비짐(viseme, 발음에 대응하는 입 모양) | `blender-facial-shapekeys` |
| 키프레임, 액션, NLA, 모션 캡처 리타기팅, 루프, 루트 모션 | `blender-animation` |
| 의상, 레이어드 의상, 바디가 의상을 뚫고 나오는 현상 | `blender-clothing` |
| 헤어, 털, 그루밍, 헤어 카드 | `blender-hair-grooming` |
| 폴리곤 예산, LOD, 드로우 콜, 정리 | `blender-game-optimization` |
| 내보내기: glTF/FBX/USD를 Roblox, Unity, Unreal, Godot, 웹으로 | `blender-export-pipelines` |
| Cycles/EEVEE 설정, 컴포지터, 일괄 렌더링 | `blender-rendering` |
| 조명, HDRI, 카메라, 턴테이블 | `blender-lighting-lookdev` |
| 툰/셀/애니메이션풍 셰이딩, 윤곽선, Line Art, Grease Pencil | `blender-stylized-npr` |
| 지형, 바이옴별 분포 배치, 모듈식 키트 | `blender-environment-kits` |
| 영상 편집(VSE), 모션 트래킹, 카메라 솔브 | `blender-video-editing` |
| 시간대, 밤, 일몰, 안개, 분위기: 사이버펑크·공포 등 | `blender-time-of-day` |
| 비, 눈, 젖은 표면, 웅덩이, 번개, 먼지/불씨 | `blender-weather-fx` |
| 천, 강체, 유체, 헤어, 지오메트리 노드 물리 | `blender-simulation` |
| 애드온 / 확장 개발 | `blender-addon-development` |
| 일괄 처리/헤드리스 파이프라인, 파일 변환 | `blender-pipeline-automation` |
| 결과물 전달 전 메시/에셋 검사: 항상 수행 | `blender-asset-qa` |
| 처음부터 끝까지의 작업 절차: 소품, 캐릭터, Roblox, 제품 이미지 | `blender-workflow-recipes` |

## 실행

**실시간 실행(blender-mcp `execute_blender_code`)**: 작은 단계로 나누어 작업하고 필요한 내용만 출력한다. 스킬 스크립트는 다음처럼 가져와 호출한다.

```python
import sys, importlib; sys.path.insert(0, r"<skills_dir>/blender-asset-qa/scripts")
import qa_check; importlib.reload(qa_check); print(qa_check.run(objects=["Chair"]))
```

각 MCP 호출은 **새 네임스페이스**에서 실행되므로 매번 `import`를 다시 한다. 모듈은 `sys.modules`에 캐시되어 있으므로 비용은 작다. `reload`는 스크립트를 수정한 뒤에만 사용한다.

**헤드리스 실행(셸을 사용할 수 있는 모든 에이전트)**: 다음 명령은 스크립트의 JSON(`@@JSON@@` 줄)만 출력한다.

```
python <skills_dir>/blender-core/scripts/run_in_blender.py --blend in.blend <script.py> -- --objects Chair --save out.blend
python <skills_dir>/blender-core/scripts/run_in_blender.py --expr "import bpy; print(len(bpy.data.objects))"
```

직접 실행하는 형식은 `blender -b in.blend --factory-startup --python-exit-code 1 -P x.py -- args`다. 이 저장소의 모든 스크립트는 `run(**kw) -> dict`와, `--` 뒤에 지정하는 동일한 플래그를 제공한다.

**세션의 첫 호출**: `scripts/env_report.py`를 실행한다. 버전, 엔진, GPU, 애드온, 단위, 색상 관리, 장면 내 항목 수를 반환한다.

## 규칙

- **오퍼레이터(operator, Blender의 실행 명령)보다 Data API 우선:** `bpy.data`, `bmesh`, `mesh.attributes`, `foreach_get/set`을 numpy와 함께 사용한다. 오퍼레이터는 컨텍스트와 선택 상태에 의존하고, 상당수는 백그라운드 모드에 없는 3D 뷰를 요구한다.
- 오퍼레이터가 불가피하면 `with bpy.context.temp_override(object=ob, active_object=ob, selected_objects=[ob], selected_editable_objects=[ob]): bpy.ops...`를 사용한다. 결과가 `{'FINISHED'}`인지 확인한다.
- **편집 모드 분리:** 편집 모드에서는 `ob.data`가 갱신되지 않는다. `bmesh.from_edit_mesh` + `bmesh.update_edit_mesh`를 사용하거나, 읽기 전에 OBJECT 모드로 전환한다.
- **노드:** 이름은 언어 설정에 따라 달라지므로 `name`이 아니라 `type`으로 찾는다(`n.type == "BSDF_PRINCIPLED"`). 소켓은 영문 이름이나 `identifier`로 찾아도 된다.
- **열거형:** `[i.identifier for i in T.bl_rna.properties[p].enum_items]`로 유효한 값을 읽는다. 동적 열거형(`render.engine`, `view_transform`, `look`)은 실제보다 적은 값을 보고하므로, `try/except TypeError` 안에서 값을 할당한다. 오류 메시지에 유효한 값 목록이 표시된다.
- **엔진:** `BLENDER_EEVEE`, `CYCLES`, `BLENDER_WORKBENCH`를 사용한다. Cycles 장치는 `scene.cycles.device = "GPU"`와 환경 설정의 `compute_device_type`으로 지정한다.
- **계산 결과가 반영된 데이터(evaluated data):** `ob.evaluated_get(depsgraph)` → `.to_mesh()` 순서로 사용하고, 마지막에는 반드시 `.to_mesh_clear()`를 호출한다. 변경 후 `matrix_world`를 읽기 전에 `view_layer.update()`를 호출한다.
- **해제된 데이터:** 모디파이어를 적용·제거하거나 오브젝트·ID를 제거하면 해당 데이터가 해제된다. 먼저 이름을 모으고(`[m.name for m in ob.modifiers]`), 이후에는 이전 Python 참조에 접근하지 않는다. 잘못된 데이터를 반환하거나 충돌할 수 있다.
- **기본 이름을 믿지 않는다.** “Cube.001” 같은 이름에 의존하지 말고 오브젝트 참조를 유지한다. 이름은 명시적으로 바꾸고 `bpy.data.objects[name]`으로 조회한다.
- **스케일:** 1단위 = 1 m다. 베벨, 거리값을 사용하는 모디파이어, 리깅, 물리, 베이크, 내보내기 전에 회전/스케일을 적용한다(`transform_apply`).
- **경로:** `bpy.path.abspath("//textures/x.png")`는 .blend 파일을 기준으로 상대 경로를 해석한다. 저장은 명시적으로 수행한다. 백업에는 `save_as_mainfile(filepath=..., copy=True)`를 사용한다.
- **실시간 세션은 사용자의 작업이다.** `read_factory_settings`를 호출하지 않고, 직접 만들지 않은 데이터를 삭제하지 않으며, 파괴적인 일괄 수정 전에 백업 사본을 저장한다.
- **백그라운드의 GPU 모듈:** 먼저 `gpu.init()`을 호출한다(5.2+). `bgl`은 더 이상 존재하지 않는다.
- **큰 메시:** 버텍스마다 `bpy.ops`를 호출하지 않는다. numpy와 `foreach_get`을 사용한다(references/bpy-patterns.md 참고).

## 기존 튜토리얼과 LLM의 기억이 맞지 않는 5.x API 변경

`action.fcurves` → channelbags · `scene.node_tree` → `scene.compositing_node_group` · `material.use_nodes`는 사용 중단 예정이며 새 재질에는 이미 노드가 있음 · `mod["Socket_2"]` → `mod.properties.inputs.Socket_2.value`(5.2) · `BLENDER_EEVEE_NEXT` → `BLENDER_EEVEE` · 불리언 `FAST` → `FLOAT` · 본 레이어 → 본 컬렉션 · `bl_info` 애드온 → 확장(`blender_manifest.toml`) · `bpy.props` 값은 더 이상 딕셔너리 방식으로 접근할 수 없음(`scene["cycles"]`). 전체 표는 [references/api-changes-5x.md](references/api-changes-5x.md)를 참고한다.

## 검증: 완료라고 말하기 전에 반드시 수행

1. 형용사 대신 숫자로 보고한다. 삼각형 수, 오브젝트 수, 재질 수, 치수(`ob.dimensions`), 저장한 출력 파일을 보고한다.
2. 지오메트리를 변경했다면 `blender-asset-qa`의 `qa_check.py`를 실행한다. Z-fighting, 분리된 부분, 비매니폴드, 뒤집힌 노멀, 스케일을 검사한다.
3. 직접 살펴본다. MCP에서는 `look`을 사용한다(`mode="angles"`, 셰이딩은 `material`/`wireframe`). 헤드리스에서는 `blender-asset-qa/scripts/review_shots.py`가 여러 화면을 한눈에 비교할 수 있는 이미지 모음(콘택트 시트)을 렌더링한다.
4. 자신의 출력물을 다시 확인한다. 내보낸 파일이 실제로 존재하고 크기가 0이 아닌지 확인한다.

## 참조 문서

- [references/api-changes-5x.md](references/api-changes-5x.md): 4.x→5.2 마이그레이션 표. 코드에서 AttributeError/KeyError가 발생하면 읽는다.
- [references/bpy-patterns.md](references/bpy-patterns.md): bmesh, 속성, numpy, temp_override, depsgraph, 드라이버, append/link, 핸들러, 타이머에 관한 검증된 예제.
