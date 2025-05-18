# prompts.py
# 该文件存储和生成与LLM交互所需的各种提示 (prompts)。

from typing import Dict, List, Any, Optional
import json
import config # 导入配置，例如 INITIAL_CONTEXT_CHAPTERS


# --- 用于小说分析的提示 (阶段 1.2) ---

def get_novel_analysis_prompt(previous_analysis_summary_json_str: str, current_chapter_text: str, current_chapter_number: int) -> str:
    """
    生成用于LLM分析一个小说章节并返回增量信息的提示。
    Args:
        previous_analysis_summary_json_str: 到目前为止的分析文档的完整JSON字符串。LLM应在此基础上进行补充。
        current_chapter_text: 当前待分析章节（或合并章节）的完整文本内容。
        current_chapter_number: 当前待分析章节的代表章节号 (由程序提供，例如合并时是第一章的号)。
    Returns:
        生成的提示字符串。
    """
    prompt = f"""
你正在协助以增量方式分析一部长篇小说的原文。
这是到目前为止积累的分析文档的JSON内容。你的任务是基于当前提供的章节文本，对这份文档进行补充和更新。请不要重复先前文档中已有的、完全相同的信息，除非是对现有条目的修正或重要补充。
<previous_analysis_summary_json_block>
{previous_analysis_summary_json_str}
</previous_analysis_summary_json_block>

现在，请严格基于以下提供的【当前章节文本（可能包含序章和第一章的合并内容，代表章节号为 {current_chapter_number}）】进行分析。
<current_chapter_text_block>
{current_chapter_text}
</current_chapter_text_block>

你的任务是：**仅输出一个JSON对象，其中包含你从【当前章节文本块】中新提取或需要更新的信息。**
程序会在外部将你的JSON输出与主分析文档智能合并。

具体要求如下：

1.  **世界观细节提取 (world_setting)：**
    *   如果当前章节文本揭示了**新的、先前未记录的**世界观信息（如规则、地点、势力），请在返回的JSON中，于 "world_setting" 对象的相应字段（如 "rules_and_systems", "key_locations", "major_factions"）以列表形式提供这些**纯新增项**。
    *   如果当前章节文本对 "overview" 有**新的、补充性的**描述，请在 "world_setting" 对象中提供 "overview" 字段，并包含这部分补充文本。

2.  **主剧情线梳理 (main_plotline_summary)：**
    *   如果当前章节文本对主剧情有重要推进，请在返回的JSON中提供 "main_plotline_summary" 字段，并包含对当前章节关键剧情发展的**补充性总结**。程序会将其追加。

3.  **时间线与关键事件精确记录 (detailed_timeline_and_key_events)：**
    *   **只输出**那些从【当前章节文本块】中新识别出的、先前未记录在 `<previous_analysis_summary_json_block>` 中的重要事件。
    *   对于每个新事件，请在返回的JSON的 "detailed_timeline_and_key_events" 列表中提供一个包含以下字段的对象（**你不需要在JSON中输出 `chapter_approx` 字段，程序会自动将其设置为 {current_chapter_number}**）：
        * `event_id`: (string, 请使用 "temp_event_描述性短语" 格式的临时ID，例如 "temp_event_主角发现卷轴")
        * `event_time_readable`: (string, 从当前章节文本中提取的、相对于本章（或合并批次代表章节 {current_chapter_number}）的具体时间信息，如“本章开端”、“三天后上午”、“黄昏时分”。如果无法确定，则使用“本章内某时”。)
        * `original_text_snippet_ref`: (string, 原文中描述此事件的关键句段摘要，不超过100字。)
        * `description`: (string, 对此事件的客观简洁描述。)
        * `is_anchor_event`: (boolean, true/false，判断是否为推动原著主线的关键转折点。)
        * `key_characters_involved`: (list of strings, 参与此事件的主要角色名。)

4.  **主要人物信息更新 (character_profiles)：**
    *   如果当前章节文本中出现了**新的、先前未记录的重要人物**，请在返回的JSON的 "character_profiles" 对象中为他们创建完整的档案结构。其 "first_appearance_chapter" 应为 {current_chapter_number}。
    *   如果当前章节文本使**已有角色**（存在于 `<previous_analysis_summary_json_block>` 中的角色）发生了关键发展或信息更新：
        *   请在返回的JSON的 "character_profiles" 对象中包含该角色名作为键。
        *   对于该角色的值，**只提供需要更新或追加的字段**。例如：
            *   如果其 "description" 需要更新，则提供新的 "description" 文本。
            *   为其 "key_developments" 列表追加新的发展条目，新条目中的 "chapter" 应为 {current_chapter_number}，并引用本章相关事件的临时 `event_id`。
            *   如果 "personality_traits" 或 "motivations" 有新增项，则提供这些新增项的列表。
            *   如果 "relationships" 有变化，则提供更新后的关系字典。
        *   **不要重复角色档案中未发生变化的信息。**

5.  **未解之谜或主题 (unresolved_questions_or_themes_from_original)：**
    *   如果当前章节文本引出了**新的、先前未记录的**未解之谜或重要主题，请在返回的JSON的 "unresolved_questions_or_themes_from_original" 列表中提供这些**纯新增项**。

请确保你的输出是一个结构良好的JSON对象，只包含基于【当前章节文本块】分析得出的新增或具体更新的信息。不要返回完整的全局分析文档。
例如，如果当前章节没有新的世界观规则，则你的JSON输出中，"world_setting" 下不应包含 "rules_and_systems" 键，或者该键对应一个空列表。
"""
    return prompt


# --- 叙事引擎的系统提示 (阶段 2.2 及之后) ---
NARRATIVE_ENGINE_SYSTEM_PROMPT = """
你的身份是“小说写手”。你的核心任务是严格遵循所提供的【小说原文风格】和【原著核心设定】，逐步撰写和叙述小说的故事情节。
你将采用全知视角或紧密跟随主角的第三人称视角进行叙述。
用户将作为主角“穿越”进入这个基于【指定小说原文】构建的世界，并通过在“...”信号词后发送自由文本来决定主角的行动和选择。

你的创作必须严格依据以下三个核心信息源：
1.  **【当前章节原文片段】**: 这是你叙事的直接蓝本和风格参照。你需要模仿其语言风格、叙事节奏和描写细腻度。此片段代表了主角当前所能感知和了解的直接环境与事件范围。
2.  **【剧情记忆档案】**: 这份档案记录了用户（主角）到目前为止的所有选择、行动、以及这些行动所产生的直接后果和剧情发展。它还可能包含当前剧情与原著时间线的偏差情况。
3.  **【小说核心设定摘要】**: 这份摘要包含了从小说原文分析得出的、与当前故事进度相关的世界观、主要人物档案（性格、动机、关系等均以原著为准）、已发生的原著时间线和关键事件，以及可能的、非常临近的未来剧情锚点提示（如有）。这些是不可违背的基石。**你不能使用此摘要中未提及的、或超出当前章节范围的未来信息。**

在你接收到用户的行动指令后，你需要：
* **理解用户意图**：准确把握用户希望主角做什么。
* **逻辑判定与剧情推进**：(具体逻辑见用户后续提供的上下文)
* **合理性处理**：(具体逻辑见用户后续提供的上下文)
* **叙事生成**：
    * 细致描写主角的行动、心理活动，以及由此产生的直接后果和环境变化。
    * 自然地包含对时间流逝的描述或当前时间的暗示（例如“次日清晨”、“黄昏酉时”、“约莫半个时辰后”，或根据上下文使用相对于“本章”的时间表述），确保与【剧情记忆档案】中记录的上一事件时间点在逻辑上连贯，并尽可能与原著时间线的流逝速度感保持一致。
    * 你的叙述应引人入胜，并自然地导向下一个用户可以进行选择或行动的节点，或者在一段叙事后明确等待用户输入。
    * **严格避免预知或提及当前提供信息范围之外的未来情节、角色或设定。**

【重要指令】：在您完成每一轮的叙事文本后，请务必另起一行，并严格按照以下格式附加一个JSON对象，包含对本轮叙事的分析元数据：
[NARRATIVE_METADATA_JSON_START]
{
  "protagonist_action_summary": "对主角本轮行动的简洁概括（例如：主角决定调查神秘洞穴）",
  "event_time_readable_context": "从叙事中推断或明确的当前易读时间点（例如：次日黄昏，约申时三刻，或 本章中段/事件发生后不久）",
  "immediate_consequences_and_observations": ["主要后果或观察点1", "主要后果或观察点2"],
  "character_state_changes": { "角色名1": {"mood": "新情绪", "status_effect": "新状态"}, "角色名2": {"location_change": "新地点"} },
  "item_changes": { "主角": { "acquired": ["物品A"], "lost": ["物品B"] } },
  "world_state_changes": ["世界状态的关键变化1", "世界状态的关键变化2"],
  "divergence_from_original_plot": {
    "level": "无/轻微/中度/显著",
    "original_timeline_event_ref": "被影响的原著事件ID（如有，来自novel_analysis.json，例如E001）",
    "description_of_divergence": "与原著剧情的具体偏差描述，或指出与哪个原著事件发生交互/偏离"
  },
  "current_chapter_progression_hint": "对当前在原著章节中进展位置的估计或提示（例如：接近本章末尾，已进入下一章开端，已完成原著事件E005）"
}
[NARRATIVE_METADATA_JSON_END]
请确保JSON对象格式正确无误，并且只包含在[NARRATIVE_METADATA_JSON_START]和[NARRATIVE_METADATA_JSON_END]标记之间。叙事文本本身不应包含这些标记。

请确保所有叙述均与【当前提供的原著设定和时间线逻辑】保持一致或作出合理解释。在你的回应中，直接开始叙述故事，不要包含任何角色扮演之外的对话或解释，除非是故事本身的旁白。
"""


# --- 用于生成初始叙事的提示 (阶段 2.3) ---
def get_initial_narrative_prompt(novel_title: str, initial_chapters_text: str, relevant_core_settings_summary: str,
                                 protagonist_initial_state: str, current_chapter_number_for_context: int) -> str:
    return f"""
你现在要开始为用户撰写一部名为《{novel_title}》的交互式小说的开篇。故事将从第 {current_chapter_number_for_context} 章的开端附近开始。
用户将扮演原著中的主角。

以下是这部小说开篇的原文内容（通常是第 {current_chapter_number_for_context} 章及其前后 {config.INITIAL_CONTEXT_CHAPTERS-1} 章的内容，具体取决于可获得性）：
<initial_chapters_text_block>
{initial_chapters_text}
</initial_chapters_text_block>

以下是与故事开端（第 {current_chapter_number_for_context} 章附近）最相关的核心设定摘要（源自对整部小说的分析，但已根据当前进度筛选）：
<core_settings_summary_block>
{relevant_core_settings_summary}
</core_settings_summary_block>

主角的初始状态设定如下（与原著故事开端一致）：
<protagonist_initial_state_block>
{protagonist_initial_state}
</protagonist_initial_state_block>

你的任务是：
1.  基于以上提供的原著开篇内容和核心设定，开始撰写故事，将用户（作为主角）引入原著设定的初始情境中（即第 {current_chapter_number_for_context} 章的开端）。
2.  你的叙述风格应模仿【initial_chapters_text_block】中的原文风格。
3.  在叙述一段初始场景和情况后，自然地引导至第一个用户（主角）可以进行选择或行动的节点。这个节点应该是原著第 {current_chapter_number_for_context} 章中的一个早期情节点，或者一个合乎逻辑的、开放的行动点。
4.  在引导至行动节点后，请明确地以“接下来，你决定做什么呢？（请输入你的行动）”或类似方式结束你的叙述，以提示用户输入。
5.  **重要：请只输出纯粹的开篇叙事文本。不要包含任何元数据标记 ([NARRATIVE_METADATA_JSON_START]等) 或JSON对象。**
6.  **严格避免预知或提及超出第 {current_chapter_number_for_context} 章（或所提供的 `initial_chapters_text_block` 和 `core_settings_summary_block` 范围之外）的未来情节、角色或设定。**

请直接开始你的叙述。
"""


# --- 用于叙事继续的用户提示内容 (阶段 3.2) ---
def get_narrative_continuation_user_prompt_content(
        current_chapter_segment_text: str,
        plot_memory_archive_summary: str,
        core_settings_summary_for_current_context: str,
        user_action: str,
        current_chapter_number_for_context: int,
        planned_reconvergence_info: Optional[str] = None
) -> str:
    contextual_info = f"""
当前故事进展至第 {current_chapter_number_for_context} 章附近。

【当前章节原文片段参考】 (主要围绕第 {current_chapter_number_for_context} 章):
{current_chapter_segment_text}

【剧情记忆档案摘要】 (记录了到目前为止的剧情发展和用户选择):
{plot_memory_archive_summary}

【当前情境相关核心设定摘要】 (基于当前第 {current_chapter_number_for_context} 章及之前已揭示的信息):
{core_settings_summary_for_current_context}
"""
    if planned_reconvergence_info:
        contextual_info += f"""

【重要剧情导向提示】: 当前剧情已与原著有一定偏离。请在本次及后续叙事中，设法巧妙地、自然地将故事线索引向以下原著关键锚点事件或情境：'{planned_reconvergence_info}'。这可能需要创造新的过渡情节或利用现有角色动机。请确保此引导过程符合当前第 {current_chapter_number_for_context} 章的逻辑和氛围。
"""
    full_user_prompt_content = f"""
{contextual_info}

现在，主角（用户）在第 {current_chapter_number_for_context} 章的当前情境下决定：
...
{user_action}

请根据以上所有信息，特别是主角的最新决定，继续撰写故事。确保叙述内容与第 {current_chapter_number_for_context} 章的背景和已知信息一致，避免跳跃到未来的章节内容。并在叙述结束后附加元数据JSON块，如先前系统提示中所述。
"""
    return full_user_prompt_content


if __name__ == "__main__":
    print("测试 prompts.py...")
    sample_prev_analysis = json.dumps({
        "world_setting": {"overview": "一个奇幻世界", "rules_and_systems":["魔法是存在的"]},
        "main_plotline_summary": "英雄开始了旅程。",
        "detailed_timeline_and_key_events": [{"event_id":"E001", "description":"初始事件", "chapter_approx":0}],
        "character_profiles": {"英雄":{"description":"勇敢的人"}},
        "unresolved_questions_or_themes_from_original": []
    }, indent=2, ensure_ascii=False)
    sample_chapter_text = "第一章 新的挑战\n英雄遇到了新的敌人。这个敌人很强大。"
    sample_chapter_num = 1
    analysis_prompt = get_novel_analysis_prompt(sample_prev_analysis, sample_chapter_text, sample_chapter_num)
    print("\n--- 小说增量分析Prompt示例 ---")
    print(analysis_prompt)
    print("\n--- (结束 小说增量分析Prompt示例) ---")
    print("\n--- 叙事引擎系统Prompt ---")
    print(NARRATIVE_ENGINE_SYSTEM_PROMPT[:600] + "...")
    print("\n--- 初始叙事Prompt示例 ---")
    initial_prompt = get_initial_narrative_prompt(
        novel_title="失落的神器",
        initial_chapters_text="很久很久以前，在一个遥远的村庄... (第一章内容)",
        relevant_core_settings_summary="世界观：魔法与剑。主要人物：艾拉（主角），一个年轻的寻宝者。时间线：故事的开端。",
        protagonist_initial_state="主角艾拉，位于溪边村，时间是春季的第一天。",
        current_chapter_number_for_context=1
    )
    print(initial_prompt[:700] + "...")
    print("\n--- 叙事继续用户Prompt内容示例 ---")
    continuation_user_content = get_narrative_continuation_user_prompt_content(
        current_chapter_segment_text="周围的森林静悄悄的，只有风吹过树叶的沙沙声。不远处似乎有一条小径。",
        plot_memory_archive_summary=json.dumps([{
            "turn_id": 1, "user_free_text": "我决定探索那条小径。",
            "protagonist_action_summary": "主角决定探索小径。",
            "generated_narrative_segment": "艾拉踏上了小径，它蜿蜒进入森林深处。"
        }], indent=2, ensure_ascii=False),
        core_settings_summary_for_current_context="当前地点：黑森林边缘。附近关键事件：据传女巫的小屋在森林深处。",
        user_action="我小心翼翼地沿着小径前进，注意观察周围是否有危险的迹象。",
        current_chapter_number_for_context=5,
        planned_reconvergence_info="找到女巫的小屋（原著锚点事件 E007，预计在第7章发生）"
    )
    print(continuation_user_content[:1000] + "...")
    print("\nprompts.py 测试完成。")