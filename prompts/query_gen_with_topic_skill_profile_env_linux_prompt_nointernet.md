我现在给你一个 topic、一组 skills、一个用户画像以及该用户电脑的文件结构摘要，请你思考该用户配置这些 skills 的目的，以及该用户可能的需求，生成 {n} 个 query。

--- Topic ---
{topic}
--- end ---

--- Skills ---
{skills_info}
--- end ---

--- 用户画像 ---
{profile_json}
--- end ---

--- 用户电脑文件结构摘要 ---
目录数量：{dir_count}个
文件类型分布：
{file_types_summary}
文件样例：
{file_samples}
--- end ---

请你根据以上信息，思考：
1. 该用户为什么会关注这个 topic？结合用户画像中的职业、兴趣、常用工具等，推断用户在该 topic 下的真实需求。
2. 这些 skills 能帮助用户完成哪些具体任务？多个skills之间是否存在逻辑关系，能否构思一个依赖多个skills的任务？
3. 用户在日常使用中，会如何组合这些 skills 来解决实际问题？
4. 用户电脑中有哪些文件可以被利用？结合文件结构摘要，思考用户可能需要对本地文件进行哪些操作。

然后生成 {n} 个自然、真实、具体的 query，请你严格遵守以下要求：
- 每个 query 必须**与给定的topic强相关**，不能偏离topic可能涉及的范围；
- 涉及query时适当参考用户画像和skills，可以帮助你设计出更符合真实场景的query；
- query需要具体，严禁宽泛性 query（如"帮我处理一下数据"），必须包含具体的操作对象、操作方式、预期结果
- {path_discription_prompt}
- **允许有一定比例的query要求写入本地文件**，建议你生成的每组queries里面有40%需要写入本地文件，60%不需要写入。
- **禁止依赖多模信息**：query不要强制性的依赖图片、音频或视频信息。也禁止在query中要求生成多模信息（不要生成图片或者视频，但使用python等画图之后保存是可以的）。
- 你的query需要在**无法连接互联网，完全离线的情况下能够完成**，此时你的query不应该依赖“获取外部信息”和“调用远程服务”的能力，但只要本地环境里已经有文件、代码、数据、依赖，你可以依赖本地环境设计query。例如：本地终端自动化、本地文档和知识整理、本地数据处理和分析、私有代码库助手、本地代码理解修改等。
- **依赖skills，鼓励query依赖多个skills**：非常鼓励你给出一些依赖skills才能解决的query。（1）鼓励你优先思考如何将多个skills有逻辑地、自然地串联起来，根据串联之后的用途构思你的query，请注意，使用多个skills的query必须真实、有逻辑、存在有效的协同关系，不要强行串联多个skills；如果无法进行串联，请你可以根据单个skills提问，或者不依赖skills提问（2）如果你构思的query依赖某几个skills，建议你以50%的概率在query中明确指出使用的skills，另外50%直接提出需求，不提及skills的名字（3）如果你的query依赖skills，请你在`required_skills`字段列出这些skills的名字，如果不依赖skills，则填入空列表。
- query种类尽量多样，不要全部是同一类型的操作。请你大开脑洞。
- query应当符合该用户画像的身份、习惯和知识水平。
- **为每个query生成质检评分标准（rubrics）**：为每个query设计10条二元判定标准（True/False），用于事后评估AI是否正确完成了该任务。rubrics需满足：
  （1）每条rubric必须是可以明确判定为True或False的客观陈述，例如”输出文件包含至少3列数据”而非”输出质量好”；
  （2）rubrics应覆盖任务的关键完成要素：核心操作是否执行、输出格式是否正确、关键内容是否包含、约束条件是否满足等；
  （3）rubrics之间不应重复，应从不同维度检验任务完成情况；
  （4）rubrics应与query的具体内容紧密相关，不要给出通用标准。

请直接输出有效的JSON，包含5个字段，”thoughs””queries””required_skills””required_files”和”rubrics”。
- thoughs可以输出你构思这道题目时的思路，请注意满足以上需求；
- queries是你构思的query本身；
- required_skills是这个query依赖的技能列表（如果不依赖skills则填入空列表）；
- required_files是这个query需要读取或修改的本地文件路径列表，请注意，只填入需要读取或修改的文件，也就是说，填入的路径必须在”用户电脑文件结构摘要”中存在，而不是新建的。
- rubrics是该query的质检评分标准列表，每条为一个可判定True/False的客观陈述。
标准格式如下：
[
  {{“queries”: “xxx”, “required_skills”: [“xxx”, “xxx”, ...], “required_files”: [“xxx”, “xxx”, ...], “rubrics”: [“标准1”, “标准2”, ...]}},
  {{“queries”: “xxx”, “required_skills”: [“xxx”, “xxx”, ...], “required_files”: [“xxx”, “xxx”, ...], “rubrics”: [“标准1”, “标准2”, ...]}},
  ...
]
