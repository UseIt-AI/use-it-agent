"""
Word COM 常量集中管理。

来源：Microsoft Office VBA Reference (wd* 常量)。
这里只收录 WordController / SnapshotExtractor / ActionExecutor 会实际用到的，
用完补全；避免塞进去几百个用不上的常量让查阅变噪。
"""

# ---------- wdStatistic ----------
WD_STATISTIC_WORDS = 0
WD_STATISTIC_PAGES = 2
WD_STATISTIC_CHARACTERS = 3
WD_STATISTIC_PARAGRAPHS = 4

# ---------- wdInformation ----------
WD_ACTIVE_END_PAGE_NUMBER = 3          # Selection.Information(3) → 当前页码
WD_ACTIVE_END_SECTION_NUMBER = 2       # Selection.Information(2) → 当前节号

# ---------- wdGoTo* ----------
WD_GOTO_PAGE = 1
WD_GOTO_SECTION = 0
WD_GOTO_BOOKMARK = -1
WD_GOTO_ABSOLUTE = 1

# ---------- wdSaveOptions ----------
WD_DO_NOT_SAVE_CHANGES = 0
WD_SAVE_CHANGES = -1

# ---------- wdWindowState ----------
WD_WINDOW_STATE_NORMAL = 0
WD_WINDOW_STATE_MAXIMIZE = 1
WD_WINDOW_STATE_MINIMIZE = 2

# ---------- wdAlignParagraph ----------
WD_ALIGN_PARAGRAPH_LEFT = 0
WD_ALIGN_PARAGRAPH_CENTER = 1
WD_ALIGN_PARAGRAPH_RIGHT = 2
WD_ALIGN_PARAGRAPH_JUSTIFY = 3
WD_ALIGN_PARAGRAPH_DISTRIBUTE = 4

# ---------- wdLineSpacing ----------
WD_LINE_SPACE_SINGLE = 0
WD_LINE_SPACE_1PT5 = 1
WD_LINE_SPACE_DOUBLE = 2
WD_LINE_SPACE_AT_LEAST = 3
WD_LINE_SPACE_EXACTLY = 4
WD_LINE_SPACE_MULTIPLE = 5

# ---------- wdOutlineLevel ----------
# 1~9 = 标题级别，10 = 正文
WD_OUTLINE_LEVEL_BODY_TEXT = 10

# ---------- 特殊"未定义"哨兵 ----------
# Word 对未定义的三态/颜色值会返回 9999999；数值读回来要挡住它。
WD_UNDEFINED = 9999999


# ---------- 映射表（给 snapshot 输出用） ----------

ALIGNMENT_NAMES = {
    WD_ALIGN_PARAGRAPH_LEFT: "left",
    WD_ALIGN_PARAGRAPH_CENTER: "center",
    WD_ALIGN_PARAGRAPH_RIGHT: "right",
    WD_ALIGN_PARAGRAPH_JUSTIFY: "justify",
    WD_ALIGN_PARAGRAPH_DISTRIBUTE: "distribute",
}

LINE_SPACING_RULE_NAMES = {
    WD_LINE_SPACE_SINGLE: "single",
    WD_LINE_SPACE_1PT5: "1.5_lines",
    WD_LINE_SPACE_DOUBLE: "double",
    WD_LINE_SPACE_AT_LEAST: "at_least",
    WD_LINE_SPACE_EXACTLY: "exactly",
    WD_LINE_SPACE_MULTIPLE: "multiple",
}
