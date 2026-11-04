---
name: blender-clothing
description: Blender 5.2의 게임 의상 제작. 바디 영역에서 의상 생성(여유분 오프셋, 두께), 스킨 웨이트 전송, 가려진 바디 면 숨기기, 천 시뮬레이션 드레이핑으로 주름 만들기, 의상의 체형 변형 셰이프 키, 레이어드 의상, 포즈를 반영한 관통 검사, 시뮬레이션 결과를 게임용 메시로 정리하는 작업을 다룬다. 셔츠, 바지, 갑옷, 의상 세트, 레이어드·교체형 의상에 사용한다.
license: MIT
metadata:
  author: blender-agent-skills
  version: "1.2.0"
---

<!-- Korean translation of SKILL.md. Source: EL4CTEO/blender-skills @ fb92cfb4cc5a238c22113a6a230b09f535bd0656. Prose translated; executable examples and API identifiers retained. -->

# 의상

실행 방식은 `blender-core`에 있다. 리그와 웨이트는 `blender-character-rigging`, 기존 방식의 천 설정은 `blender-simulation`, Roblox 레이어드 의상 케이지는 `blender-export-pipelines`의 references/roblox.md를 참고한다.

## 각각 한 번의 호출로 실행

```
scripts/garment.py -- --body Body --group Torso --name Shirt --hide-body
scripts/garment.py -- --body Body --zmin 0.45 --zmax 1.05 --name Pants --offset 0.01 --drape 40 --morphs
scripts/garment.py -- --body Body --group Torso --name Armor --offset 0.02 --thickness 0.008
scripts/garment.py -- --check Shirt --body Body          # pose the rig first: checks the current pose
```

## 전문가의 게임 의상 제작 절차

1. **형태:** 몸에 맞는 옷은 바디에서 추출하고 오프셋을 주어 시작한다. 헐렁한 옷은 천 시뮬레이션으로 봉제한 평면 패턴에서 시작한다. Marvelous Designer나 봉제 스프링을 사용하는 Blender 천 시뮬레이션을 쓸 수 있다. 바디를 **레스트 포즈**(rest pose, 변형 전 기준 자세인 A/T 포즈)에 둔 상태로 시뮬레이션한다.
2. **게임용 메시:** 고해상도/시뮬레이션 결과를 리토폴로지해 깨끗하고 균일한 사각형 메시로 만들고 관절에 루프를 배치한다. 팔꿈치, 무릎, 어깨에는 루프 3개를 둔다. 그다음 UV를 만든다. 저해상도 메시를 가볍게 유지하도록 주름을 노멀 맵에 베이크한다(`blender-texture-baking`).
3. **스키닝:** 바디에서 같은 본과 같은 영향 관계의 웨이트를 복사하고 정리한다. 영향 수를 4로 제한하고, 정규화하며, 0.001 미만의 웨이트는 제거한다. 그런 다음 스커트·코트처럼 헐렁한 부분에만 더 부드러운 웨이트를 섞고 해당 부분을 위한 추가 본을 배치한다.
4. **가려진 부분 숨기기:** 의상 아래의 바디 면을 삭제해 삼각형 수를 줄이고 관통을 막거나, 의상별로 마스킹한다. 소맷단과 옷깃 아래에는 피부 면을 한 링 남긴다.
5. **움직임 검증:** 변형 한계를 확인하는 포즈를 적용하고(`blender-character-rigging`의 `stress_poses.py`), 각 포즈에서 `--check`를 실행한다. 여유분(오프셋)을 늘리거나, 해당 바디 영역을 매끄럽게 다듬거나, 웨이트를 조정하거나, 가려서 해결한다.

## garment.py

- 영역: `--group`으로 지정한 바디 버텍스 그룹(웨이트 > 0.5) 또는 월드 좌표의 `--zmin/--zmax` 구간을 사용한다. 면은 월드 공간에서 복사되고, 버텍스 노멀 방향으로 `--offset`만큼 바깥으로 이동한다. 여유분의 기준은 몸에 맞는 면 의상 5–10 mm, 재킷 10–20 mm, 갑옷 15–30 mm다. 이어서 `Solidify`로 `--thickness`만큼 바깥쪽으로 두께를 더한다. 원단은 2–4 mm, 가죽/갑옷은 5–10 mm가 기준이다. UV는 바디에서 이어받는다.
- 웨이트: Data Transfer(`POLYINTERP_NEAREST`, 이름이 일치하는 모든 그룹)를 적용한 뒤, 영향 수를 `--max-influences`로 제한하고 정규화·정리한다. 바디의 Armature 모디파이어를 추가하고 리그에 부모 연결한다.
- `--hide-body`: 해당 영역을 한 링만큼 줄인 `Hidden_<name>` 버텍스 그룹과, 바디의 반전된 Mask 모디파이어를 사용한다. 교체형 의상은 마스크를 켜고 끈다. 내보낼 때는 대신 바디 사본에서 해당 면을 삭제한다.
- `--drape N`: 면과 비슷한 설정의 기존 천 시뮬레이션을 사용한다. 질량 0.15, 장력 15, 굽힘 0.5, 품질 8이다. 위쪽 8%를 고정하고, 바디 충돌 간격을 3 mm로 설정하며, N프레임 동안 안정화한 뒤 결과를 적용한다. 헐렁한 부분에 중력으로 인한 주름이 생긴다. 30–60프레임을 사용한다.
- `--morphs`: 바디의 각 셰이프 키에 대응하는 같은 이름의 의상 셰이프 키를 만든다. 레스트 포즈에서 Surface Deform을 바인딩하고, 모프마다 셰이프 키로 적용한다. 엔진에서는 바디와 의상 키를 함께 구동한다. 살찜/마름, 근육, 호흡 등이 이에 해당한다. 측정 결과, 바디를 30% 모핑하면 버텍스 346개가 의상을 관통했다. 대응하는 의상 키를 사용하면 0개였다.
- **관통 검사:** 모든 제작 작업의 끝에서도 실행한다. 각 바디 버텍스의 노멀을 따라 레이를 쏜다. 바깥쪽보다 안쪽 방향에서 의상에 먼저 닿거나, 의상과의 거리가 0.5 mm 미만이면 관통으로 판단한다. 0.1 m 이내에서 의상과 만나지 않는 버텍스는 덮이지 않은 영역으로 보고 무시한다. `covered_verts`, `poke_verts`, `poke_max_m`를 보고하며, **현재 변형 결과가 반영된** 포즈를 사용하고 바디 마스크를 반영한다.

## 레이어드 의상

- 피부에서 바깥쪽으로 속옷/기본 의상 → 셔츠 → 조끼 → 재킷 → 갑옷 순으로 배치한다. 각 레이어는 바로 아래 레이어를 기준으로 오프셋을 준다. 예를 들어 셔츠 위에 조끼를 만들 때는 `garment.py --body Shirt`를 실행한다. 웨이트는 아래 레이어가 아니라 바디에서 복사한다.
- 움직일 때 레이어끼리 관통하는 현상은 대개 웨이트 불일치에서 생긴다. 모든 레이어가 같은 바디에서 웨이트를 복사하면 함께 움직인다.
- Roblox 레이어드 의상에는 Roblox 템플릿 케이지로 만든 `<Name>_InnerCage` + `<Name>_OuterCage`가 필요하다. 버텍스 순서와 UV가 같아야 한다. 다른 엔진(UE Mutable/Unity)은 셰이프 키를 혼합하거나 바디 숨김 마스크를 사용한다. 원리는 같다.

## 주의할 점

- `shape_key_add()`는 값이 1.0인 키를 만든다(측정 결과). Python에서 모프를 만들 때는 `.value = 0`으로 설정한다.
- Surface Deform은 **모프에만** 사용한다. Armature 모디파이어와 함께 활성 상태로 남겨두면 포즈가 두 번 적용된다. `--morphs`는 키를 베이크한 뒤 Surface Deform을 제거한다.
- 제작 전에 바디의 스케일을 적용한다. 오프셋과 두께의 단위는 미터다.
- 천 시뮬레이션에는 적당한 해상도의 바디 충돌 메시가 필요하다. 바디가 50k 버텍스를 초과하면 충돌용 프록시를 만들고 Decimate로 단순화한다.
- 완성한 의상에 `blender-asset-qa`를 실행해 바디와의 Z-fighting, 떠 있는 부분, 노멀을 확인하고, 삼각형 수가 `blender-game-optimization`의 예산에 맞는지 검사한다.
