"""Small, explicitly layered gameplay confirmations supplied by the user.

These are model inputs, not copies of the upstream formal library and not
official-website claims. Consumers must preserve the rule ID and source layer.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UserConfirmedRule:
    rule_id: str
    claim: str
    source_layer: str = "user_confirmed_gameplay"
    source_path: str = "conversation:2026-07-13"


@dataclass(frozen=True)
class AuctionPoolRule:
    auction_index: int
    fee_tiers: tuple[int, ...]
    minimum_by_fee_tier: tuple[tuple[int, int], ...]
    rule: UserConfirmedRule
    typical_distinct_faction_count: int | None = None
    typical_neutral_card_count: int | None = None
    hero_offer_slot_count: int | None = None
    duplicate_faction_status: str = "unknown"


SUMMON_ATTACK_SPEED_RULE = UserConfirmedRule(
    "user-rule:summon-attack-speeds-2026-07-13",
    "米莱狄机器人、蒙恬小兵和山鬼每秒攻击 0.6 次；鲁班大师机器人每秒攻击 0.8 次。",
)

RESISTANCE_MULTIPLIER_RULE = UserConfirmedRule(
    "user-rule:resistance-multiplier-confirmed-2026-07-13",
    "模型减伤倍率 40 / (max(0, 抗性) + 40) 已由用户确认。",
    source_layer="user_confirmed_model_rule",
)

ATTACK_SPEED_CAP_RULE = UserConfirmedRule(
    "user-rule:standard-attack-speed-cap-4-2026-07-29",
    "英雄最终攻击速度的标准上限为每秒 4.0 次；明确改写上限的特殊装备另行建模。",
)

SIKONGZHEN_LIGHTNING_CHAIN_RULE = UserConfirmedRule(
    "user-rule:sikongzhen-physical-attack-plus-lightning-chain-2026-09-21",
    "勘误：司空震变身后仍保留物理普攻，额外附加法术闪电链；100级持续整回合不改变这一伤害构成。",
    source_path="conversation:2026-09-21",
)

AUCTION_HERO_COMPOSITION_RULE = UserConfirmedRule(
    "user-rule:auction-hero-composition-2026-07-13",
    "前两次英雄拍卖通常出现五个不同阵营和一张无阵营牌；偶尔会出现重复阵营。"
    "重复阵营替换原有六个展示槽中的一张；重复频率和具体阵营抽样规则尚未确认。",
)


FIRST_AUCTION_POOL_RULE = AuctionPoolRule(
    1,
    (2, 3),
    ((3, 2),),
    UserConfirmedRule(
        "user-rule:first-auction-pool-2026-07-13",
        "第一次拍卖随机提供二费、三费英雄，其中至少两张三费英雄。",
    ),
    typical_distinct_faction_count=5,
    typical_neutral_card_count=1,
    hero_offer_slot_count=6,
    duplicate_faction_status="possible_replaces_existing_slot_frequency_unknown",
)

SECOND_AUCTION_POOL_RULE = AuctionPoolRule(
    2,
    (4, 5),
    ((5, 2),),
    UserConfirmedRule(
        "user-rule:second-auction-pool-2026-07-13",
        "第二次拍卖随机提供四费、五费英雄，其中至少两张五费英雄。",
    ),
    typical_distinct_faction_count=5,
    typical_neutral_card_count=1,
    hero_offer_slot_count=6,
    duplicate_faction_status="possible_replaces_existing_slot_frequency_unknown",
)


THIRD_AUCTION_SPECIAL_EFFECT_RULE = UserConfirmedRule(
    "user-rule:third-auction-special-effect-cards-2026-07-13",
    "第三次拍卖会出现无法再通过商店刷新或天赋获得的特殊效果牌。"
    "众星拱月、能量超新星、化铁为金和军械库是已观察示例；"
    "只有实际拍卖展示和选取才能把具体效果牌计入当前局面。",
)


THIRD_AUCTION_SPECIAL_EFFECT_EXAMPLES = (
    "众星拱月",
    "能量超新星",
    "化铁为金",
    "军械库",
)

EFFECT_CARD_SHOP_RULE = UserConfirmedRule(
    "user-rule:effect-cards-use-shop-level-probability-2026-07-13",
    "效果牌会出现在商店刷新中，并按对应棋手等级的商店概率行处理。",
)

EQUIPMENT_SOURCE_RULE = UserConfirmedRule(
    "user-rule:equipment-sources-2026-07-13",
    "装备来自开局一件、每次拍卖一件、天赋、武装重构或精选武装等明确效果，及其他明确写出的少量来源。",
)

SACRIFICE_MAIN_CARRY_RULE = UserConfirmedRule(
    "user-rule:sacrifice-growth-main-carry-2026-07-13",
    "在有牺牲事件且卡面条件满足时，默认将可选牺牲成长分配给声明的主 C。",
)

GENERATED_COIN_PRIMARY_CARRY_RULE = UserConfirmedRule(
    "user-rule:generated-coin-default-primary-carry-2026-07-14",
    "玩家明确选择主要资源承接者时，生成且可使用的古币默认对该英雄使用；"
    "未选择承接者时不得猜测目标或自动使用古币。",
)

AFFINITY_TOTEM_ATTACK_METER_RULE = UserConfirmedRule(
    "user-rule:affinity-totem-attack-meter-2026-07-13",
    "因缘图腾在场时，每个己方单位（包括召唤物）完成一次普攻动作，图腾蓝条加 10；"
    "蓝条满 250 时触发全队等级效果，战斗结束清零。多段、弹射和多目标命中不额外增加普攻次数。",
)

RANDOM_HERO_TARGET_SELECTION_RULE = UserConfirmedRule(
    "user-rule:random-hero-target-selection-2026-07-13",
    "“随机 N 名英雄”从当前场上英雄中无重复选择，施法者本人可被选择；"
    "目标不足时每个已有合法目标各结算一次，缺少的名额浪费；每次触发都重新独立选择。",
)

WUZETIAN_COIN_BASE_LEVEL_RULE = UserConfirmedRule(
    "user-rule:wuzetian-coin-base-level-2026-07-13",
    "武则天在场时，古币基础永久等级额外 +1；武则天觉醒时额外 +2。"
    "该加成只作用于古币基础永久等级，不作用于李白额外提供的临时等级。",
)

LOOSE_CHANGE_DAMAGED_COIN_RULE = UserConfirmedRule(
    "user-rule:loose-change-damaged-coin-level-boundary-2026-07-13",
    "零钱兑换将获得的古币改为两张破损古币。破损古币不提供古币基础永久等级，"
    "也不吃武则天基础永久等级加成，但每次使用仍会触发李白的临时等级监听；"
    "两张破损古币可分别选择不同的合法目标。",
)

AKOMEIA_CORE_ROUND_START_RULE = UserConfirmedRule(
    "user-rule:akomeia-core-round-start-distribution-2026-07-13",
    "阿科米亚核心在回合开始时，按临时等级平均分给场上的日落海英雄；"
    "核心等级没有上限；余数按四舍五入处理，但本次分配总量不得超过核心当前总等级；"
    "特殊装备携带者和天赋另有例外。未跨越卡面阈值、目标资格或合法性时，"
    "用户允许核心分配存在 1 至 2 级的模型近似。",
)

AUCTION_REFUND_PERCENT_BY_FINISH_FROM_LAST = (
    ("last", 30),
    ("second_last", 25),
)

AUCTION_SELECTION_AND_REFUND_RULE = UserConfirmedRule(
    "user-rule:auction-selection-and-proportional-refund-2026-07-13",
    "每次拍卖只能从可选展示池拿一张；竞价先按出价支付，随后按名次比例返还给场上棋手。"
    "当前仅确认最后一名返还 30%、倒数第二返还 25%；其余名次比例和能量取整规则仍未知。",
)

AUCTION_EQUIPMENT_RULE = UserConfirmedRule(
    "user-rule:auction-random-equipment-2026-07-13",
    "每次拍卖随机发放一件装备。",
)

EFFECT_CARD_SHOP_SLOT_AND_COST_RULE = UserConfirmedRule(
    "user-rule:effect-card-shop-slot-and-cost-2026-07-13",
    "效果牌占用商店展示槽位；除特别指定外，出售返还 1 能量，购买价格为 1 至 8 能量，刷新价格为 1 能量。",
)


def confirmed_summon_attacks_per_second(
    source_unit_name: str | None,
    description: str,
) -> float | None:
    """Return an explicitly confirmed summon rate, without inferring damage or uptime."""
    if source_unit_name == "米莱狄" and "机器人" in description:
        return 0.6
    if source_unit_name == "蒙恬" and "士兵" in description:
        return 0.6
    if "山鬼" in description:
        return 0.6
    if source_unit_name == "鲁班大师" and "机器人" in description:
        return 0.8
    return None


__all__ = [
    "AFFINITY_TOTEM_ATTACK_METER_RULE",
    "ATTACK_SPEED_CAP_RULE",
    "AKOMEIA_CORE_ROUND_START_RULE",
    "AUCTION_HERO_COMPOSITION_RULE",
    "AUCTION_EQUIPMENT_RULE",
    "AUCTION_REFUND_PERCENT_BY_FINISH_FROM_LAST",
    "AuctionPoolRule",
    "AUCTION_SELECTION_AND_REFUND_RULE",
    "EFFECT_CARD_SHOP_RULE",
    "EFFECT_CARD_SHOP_SLOT_AND_COST_RULE",
    "EQUIPMENT_SOURCE_RULE",
    "FIRST_AUCTION_POOL_RULE",
    "GENERATED_COIN_PRIMARY_CARRY_RULE",
    "LOOSE_CHANGE_DAMAGED_COIN_RULE",
    "RANDOM_HERO_TARGET_SELECTION_RULE",
    "RESISTANCE_MULTIPLIER_RULE",
    "SACRIFICE_MAIN_CARRY_RULE",
    "SECOND_AUCTION_POOL_RULE",
    "SIKONGZHEN_LIGHTNING_CHAIN_RULE",
    "SUMMON_ATTACK_SPEED_RULE",
    "THIRD_AUCTION_SPECIAL_EFFECT_EXAMPLES",
    "THIRD_AUCTION_SPECIAL_EFFECT_RULE",
    "UserConfirmedRule",
    "WUZETIAN_COIN_BASE_LEVEL_RULE",
    "confirmed_summon_attacks_per_second",
]
