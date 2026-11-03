# 방어 공식 조사 (2026-11)

- 조사일: 2026-11-03. 목적: B1(공통 스탯과 전투 계산)의 방어 공식 형태를 정하기 위해, 여러 장르의 게임이 받는 피해를 어떻게 줄이는지 본다.
- 방법: 웹 검색. 출처는 대부분 커뮤니티 위키와 공략이며 개발사 공식 문서가 아니다. 게임을 실행해 확인하지 않았다.
- **페이지를 직접 열어 확인한 것**은 Vampire Survivors와 Terraria 두 곳이다. 나머지는 검색 결과의 요약을 기준으로 했고, 출처끼리 상수가 다르면 그렇다고 적었다.
- 아래 숫자는 다른 게임의 사실이며 이 프로젝트의 기획값이 아니다.

## 형태별 분류

| 형태 | 받는 피해 | 게임 (장르) | 상수·상한 |
|---|---|---|---|
| ① 고정값 감산 | 공격 − 방어 × f, 최소값 있음 | Terraria (샌드박스 액션) | f = 0.5 / 0.75 / 1 (난이도별), 최소 1. **직접 확인** |
| | | Vampire Survivors (서바이버라이크) | 방어 1당 −1, 적에게 받는 피해는 최소 1. **직접 확인** |
| | | Fire Emblem (전략 RPG) | 공격 − 방어. 작품에 따라 최소 0 또는 1 |
| ② 비율 (고정 K) | 공격 × K / (K + 방어) | League of Legends (MOBA) | K = 100 |
| | | Risk of Rain 2 (액션 로그라이크) | K = 100. 음수 방어는 피해 증가 |
| | | Brotato (서바이버라이크) | K = 15. 음수 방어는 별도 공식으로 피해 증가 |
| | | Monster Hunter (액션) | K = 80 (World 이후 근접 기준, 작품마다 다름) |
| | | Warframe (루터 슈터) | K = 300 (플레이어 기준, 적은 다른 공식) |
| | | Dota 2 (MOBA) | 1 / (1 + 0.06 × 방어), 즉 K ≈ 16.7. 음수 방어 공식은 출처끼리 다름 |
| ③ 비율 (레벨에 따라 K 증가) | 공격 × K / (K + 방어), K = a × 레벨 + b | World of Warcraft (MMO) | 레벨 1~59: K = 85 × 공격자 레벨 + 400. 상한 75% |
| | | Diablo 3 (ARPG) | K = 50 × 레벨 (몬스터 레벨인지 캐릭터 레벨인지 출처가 엇갈림) |
| ④ 공격/방어 비 | (공격 / 방어)에 비례 | Pokémon (RPG) | ⌊((2L+10)/250) × (A/D) × 위력 + 2⌋ × 보정 |
| | | Dark Souls 3, Elden Ring (액션 RPG) | 공격/방어 비에 대한 계단형 곡선. 데이터마이닝 추정이며 미확인 |
| ⑤ 타격 크기에 따라 달라짐 | 감소율 = 방어 / (방어 + c × 이번 타격 피해) | Path of Exile 2 (ARPG) | c = 10, 물리 감소 상한 90%. PoE 1의 c(5 또는 10)는 확인하지 못함 |
| ⑥ 직접 퍼센트 | 공격 × (1 − 감소율), 상한 있음 | Darkest Dungeon (턴제 RPG) | PROT %, 상한 80%. 출혈·역병은 무시 |
| | | Hades (액션 로그라이크) | 방어 스탯 없음. 피해 저항 %(God Mode 20% → 최대 80%) |
| ⑦ 흡수량 | 피해를 먼저 흡수하는 수치 | Slay the Spire (덱빌딩) | Block. 검색 결과로 확인하지 못함(일반 지식) |

## 형태별 성질

| 형태 | 방어 1의 가치 | 잡몹 대 보스 | 맞는 숫자 규모 | 장점 | 단점 |
|---|---|---|---|---|---|
| ① 고정값 | 상대 공격력에 따라 다름 | 잡몹에 매우 강하고 보스에 약함 | 작고 범위가 좁은 숫자 | 직관적, 암산 가능 | 성장 폭이 크면 잡몹이 무력해짐. 방어를 예산에 넣기 어려움 |
| ② 비율 고정 K | 실질 체력 +1/K로 일정 | 같은 비율 | 큰 숫자, 넓은 범위 | 실질 체력이 방어에 정비례해 예산화 쉬움, 무적 없음 | 퍼센트 표시가 필요함. 스탯이 K보다 훨씬 커지면 K 재조정 |
| ③ 레벨 K | 같은 레벨 장비끼리 일정 | 같은 비율 | 레벨 성장이 큰 게임 | 오래된 장비가 자연히 밀려남 | 레벨(또는 구역) 개념이 필요 |
| ④ 공/방 비 | 상대 공격력 대비 | 비율 | 스탯 인플레이션이 큰 게임 | 양쪽이 같이 커져도 유지 | 공식 복잡, 예산화 어려움 |
| ⑤ 타격 크기 | 작은 타격일수록 큼 | 잡몹에 강함 | 다양한 타격 크기 | 잡몹 방어와 보스 방어를 일부러 분리 | 계산 복잡, 직관 낮음 |
| ⑥ 직접 % | 퍼센트 그대로 | 같은 비율 | 무관 | 단순 | 쌓이면 무적이라 상한과 곱·합 규칙이 필수 |

## 장르별 경향

- **MOBA·ARPG·MMO·루터 슈터**: 거의 다 비율형(②, ③)이다. 장비 성장 폭이 크고 상대가 다양하기 때문이다.
- **서바이버라이크**: 둘 다 있다. Vampire Survivors는 고정값(①)이지만 방어 수치 자체를 작게 묶어 둔다(방어 아이템의 레벨 상한이 낮다). Brotato는 비율형(②, K가 작음)이다.
- **액션 로그라이크**: Risk of Rain 2는 비율형(②), Hades는 방어 스탯 없이 직접 퍼센트(⑥)다.
- **턴제 전략·RPG**: 고정값(Fire Emblem)이나 공격/방어 비(Pokémon)다. 숫자가 작고 한 번의 교환이 중요한 장르다.
- **공통 장치**: 고정값형은 최소 피해(0 또는 1)를 두고, 감소율이 끝없이 오를 수 있는 형태(③, ⑤, ⑥)는 상한을 둔다(위 표의 WoW, PoE 2, Darkest Dungeon, Hades). 비율형은 구조상 상한이 필요 없다.

## 시험 프로젝트(`my-roguelike`)에 대한 시사점

도구는 여러 형태를 지원하고 게임마다 고르게 한다. 아래는 스킬을 시험하는 게임 프로젝트 `my-roguelike`(컨셉 `ripening_gems`)에 어느 형태가 맞는지에 대한 판단이다. 다른 게임에는 그 게임의 숫자 규모와 장르로 다시 판단한다.

`my-roguelike`는 "약하게 시작해 화면을 쓸어버리게 되는" 서바이버라이크에 메타 성장, 티어, 강화, 합성이 겹친다. 스탯 범위가 넓고 잡몹과 보스가 같이 나온다.

- 고정값(①)은 Vampire Survivors처럼 방어를 작은 정수로 묶어 둘 때만 무리 없이 돈다. 강화·합성으로 방어가 크게 오를 수 있으면 잡몹이 무력해진다.
- 비율 고정 K(②)는 "방어 1 = 실질 체력 1/K"로 가치가 일정해서 B2의 스탯 예산과 가장 잘 맞는다. 같은 장르의 Risk of Rain 2와 Brotato가 이 형태다.
- 성장 폭이 아주 크면 구역을 레벨처럼 써서 K를 구역마다 키우는 ③으로 넓힐 수 있다. 이건 B2에서 곡선을 보고 정해도 된다.
- 잡몹에만 강한 방어를 일부러 만들고 싶을 때만 ①이나 ⑤가 의미 있다.

도구가 지원할 형태(안): ① 고정값(f, 최소 피해), ② 비율(K), ③ 레벨·구역 비율(K = a × 레벨 + b), ⑥ 직접 퍼센트(상한). ④와 ⑤는 계산이 복잡해 처음에는 넣지 않는다.

## 출처

- League of Legends: [Armor (LoL Wiki)](https://wiki.leagueoflegends.com/en-us/Armor)
- Dota 2: [armor magic resistance math (teamsmurf)](https://teamsmurf.com/armor-magic-resistance-math-dota-2/), [Base armor (Dota 2 Wiki)](https://dota2.fandom.com/wiki/Base_armor)
- Risk of Rain 2: [Armor (RoR2 Wiki)](https://riskofrain2.wiki.gg/wiki/Armor), [Risk of Rain 2 Armor (eXputer)](https://exputer.com/guides/risk-of-rain-2-armor/)
- Brotato: [Armor (Brotato Wiki)](https://brotato.wiki.spellsandguns.com/Armor)
- Vampire Survivors: [Armor (stat)](https://vampire.survivors.wiki/w/Armor_(stat)), [Armor (item)](https://vampire.survivors.wiki/w/Armor_(item))
- Terraria: [Defense (Terraria Wiki)](https://terraria.wiki.gg/wiki/Defense)
- Fire Emblem: [Attack (Fire Emblem Wiki)](https://fireemblemwiki.org/wiki/Attack), [The Weapon Triangle (GamePress)](https://gamepress.gg/feheroes/node/3106)
- Monster Hunter: [Monster Hunter Wilds 토론 (Steam)](https://steamcommunity.com/app/2246340/discussions/0/599646477861547247), [防御力 (wikiwiki.jp)](https://wikiwiki.jp/nenaiko/%E3%82%B7%E3%82%B9%E3%83%86%E3%83%A0/%E9%98%B2%E5%BE%A1%E5%8A%9B)
- Warframe: [Armor (Warframe Wiki)](https://wiki.warframe.com/w/Armor)
- World of Warcraft: [Damage reduction (Warcraft Wiki)](https://warcraft.wiki.gg/wiki/Damage_reduction)
- Diablo 3: [Armor (Diablo Wiki)](https://di.diablowiki.net/Armor), [damage reduction explained (Maxroll)](https://maxroll.gg/d3/resources/damage-reduction-explained)
- Pokémon: [Damage (Bulbapedia)](https://bulbapedia.bulbagarden.net/wiki/Damage)
- Elden Ring: [Physical Defense (Fextralife)](https://eldenring.wiki.fextralife.com/Physical+Defense)
- Path of Exile 2: [Armour (PoE2 Wiki)](https://poe2wiki.net/wiki/Armour), [Armour guide (Mobalytics)](https://mobalytics.gg/poe-2/guides/armour)
- Darkest Dungeon: [Darkest Dungeon Wiki](https://darkestdungeon.wiki.gg/wiki/Critical_Chance)
- Hades: [Hades 2 God Mode (Dexerto)](https://www.dexerto.com/gaming/how-to-make-hades-2-easier-god-mode-explained-2695050/)
- 실질 체력이 비율형에서 방어에 정비례한다는 설명: [Armor (LoL Wiki, 구판)](https://wiki.leagueoflegends.com/en-us/Armor?oldid=4073057)
