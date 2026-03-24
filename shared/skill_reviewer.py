# -*- coding: utf-8 -*-
import os
import sys
import json
import asyncio
import argparse
from pathlib import Path

import httpx
from openai import AsyncOpenAI

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from config.config_loader import load_config

FUNCTION_LIST = """
1. 邮件操作（发邮件）：编写、发送、抄送、附件上传、定时发送、邮件模板调用等完整邮件处理功能。
2. 票务相关：提供车票、机票、演出、电影、景点等票务信息查询、预订、改签、退票及订单状态跟踪服务。
3. 购物：商品搜索、加购、下单、订单管理、物流查询、优惠券使用等线上购物全流程操作。
4. 产品对比：对多平台、多型号商品的参数、价格、口碑、配置等信息进行抓取、整理与横向对比，生成对比结论。
5. 个性化资讯：根据用户兴趣、行业、关注领域，自动筛选、汇总、推送定制化新闻、文章、动态等内容。
6. 股市操作：提供股票、基金、指数等行情查询、数据可视化、持仓分析、资讯解读、交易提醒等理财辅助功能。
7. 地图查询：支持地点搜索、定位查看、路线预览、POI 查询、距离测算、实时路况展示等地图基础能力。
8. 出行规划：根据出发地、目的地、时间、偏好，智能规划交通方式、行程顺序、换乘方案与整体出行安排。
9. 娱乐与休闲：影视、音乐、游戏、兴趣推荐、休闲内容浏览、放松类互动等娱乐相关内容与服务。
10. 抠图剪辑：对图片、视频进行裁剪、拼接、滤镜、调色、字幕、特效处理、格式转换等多媒体编辑操作。
11. 健康管理：记录并分析运动、睡眠、饮食、体重、体征等健康数据，生成健康报告、提醒与改善建议。
12. 日程管理：支持日程添加、时间规划、待办事项管理、重复任务、闹钟提醒、日程视图展示等时间管理功能。
13. 智能控制：对智能家居、设备进行状态查看、指令下发、自动化联动与远程控制。
14. 社区互动：支持在论坛、社交平台、兴趣社区进行发帖、评论、点赞、分享、内容浏览等互动行为。
15. 缴费与生活服务：水电费、话费、网费、物业费等线上缴费，以及各类生活便民服务办理。
16. 知识点梳理：对特定领域的知识进行系统性归纳、关联与可视化，构建清晰的知识框架。
17. 习题求解：通过分步引导和思路提示，辅助用户理解和解答各类学术与逻辑问题。
18. 学习计划：根据目标、时间和基础，协助制定个性化的学习路径与时间管理方案。
19. 学术调研：帮助快速把握领域概况、界定研究问题并查找评估关键文献。
20. 文献写作：创作研究报告、论文、科研综述、创意写作等。或在文本的构思、起草与润色过程中提供结构、表达与规范方面的辅助。
21. 实验方案设计与实施：为科学研究中的实验环节提供从假设、设计到操作流程的全链条思路支持。
22. 实验数据分析与处理：协助完成从数据清洗、统计分析、结果可视化到科学解读的全过程。
23. 科研工具使用：针对特定软件、数据库或编程语言，提供操作指导、代码示例与故障排查。
""".strip()

SYSTEM_PROMPT = """你是一个技能分析专家。用户会提供一个 SKILL.md 文件的内容，你需要根据该技能的描述，判断它可能用于以下哪些功能场景。
可选的功能场景列表：
{functions}

请严格按照以下 JSON 格式返回结果，不要输出任何其他内容：
{{
  "skill名称": "从内容中提取的技能名称",
  "skill简介": "一句话描述该 skill 的功能用法，让人知道该 skill 的使用边界。如果是针对特定软件、网页或工具比如“推特浏览 skill”，必须写出其专用于“推特”。描述控制在150字以内",
  "skill账号依赖": "如果需要各类账户信息才能使用则注明所需账号要求，否则置为空",
  "skill可用场景": ["匹配的场景名称", "匹配的场景名称"]
}}

注意：
- "skill可用场景" 只能从上面 22 个功能场景名称中选取，只需填写场景名称。
- 如果该技能不匹配任何场景，返回空数组 []。
- 可以匹配多个场景。
- 只返回 JSON，不要有多余文字。""".format(functions=FUNCTION_LIST)


def _resolve_config_path(path_str: str | None) -> str | None:
    if not path_str:
        return path_str
    path = Path(path_str)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return str(path.resolve())


def _load_runtime_config() -> tuple[dict, dict, dict]:
    cfg = load_config()
    api_cfg = cfg.get("api_config", {})
    pipeline_cfg = cfg.get("pipeline_config", {})
    reviewer_cfg = cfg.get("skill_reviewer_config", {})
    return api_cfg, pipeline_cfg, reviewer_cfg


def _build_client(api_cfg: dict) -> tuple[AsyncOpenAI, str]:
    api_key = os.getenv("LLM_API_KEY", api_cfg.get("LLM_API_KEY", ""))
    base_url = os.getenv("LLM_BASE_URL", api_cfg.get("LLM_BASE_URL", ""))
    model = os.getenv("LLM_MODEL", api_cfg.get("LLM_MODEL", "gpt-4o"))
    proxy = os.getenv("LLM_PROXY", api_cfg.get("LLM_PROXY", None))

    client = AsyncOpenAI(
        api_key=api_key,
        base_url=base_url or None,
        http_client=httpx.AsyncClient(
            verify=False,
            proxy=proxy or None,
        ),
    )
    return client, model


def find_skill_files(target_dir: str) -> list[dict]:
    results = []
    for root, _, files in os.walk(target_dir):
        for file_name in files:
            if file_name.upper() == "SKILL.MD":
                full_path = os.path.join(root, file_name)
                rel_dir = os.path.relpath(root, target_dir)
                if rel_dir == ".":
                    rel_dir = ""
                results.append({"full_path": full_path, "rel_dir": rel_dir, "filename": file_name})
    return results


async def review_skill(client: AsyncOpenAI, content: str, model: str) -> dict:
    response = await client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"以下是 SKILL.md 的内容：\n\n{content}"},
        ],
    )
    text = response.choices[0].message.content.strip()
    return json.loads(text)


async def process_one(
    sem: asyncio.Semaphore,
    client: AsyncOpenAI,
    sf: dict,
    model: str,
    index: int,
    total: int,
) -> dict | None:
    async with sem:
        label = f"{sf['rel_dir'] or '.'}/{sf['filename']}"
        print(f"[{index}/{total}] 处理：{label}")
        try:
            with open(sf["full_path"], "r", encoding="utf-8") as f:
                content = f.read()

            if not content.strip():
                print("  跳过：文件内容为空")
                return None

            review = await review_skill(client, content, model)
            result = {
                "skill名称": review.get("skill名称", ""),
                "skill目录": sf["rel_dir"],
                "skill简介": review.get("skill简介", ""),
                "skill账号依赖": review.get("skill账号依赖", ""),
                "skill可用场景": review.get("skill可用场景", []),
            }
            scenes = ", ".join(result["skill可用场景"]) or "无匹配"
            print(f"  完成：{result['skill名称']} -> {scenes}")
            return result
        except Exception as exc:
            print(f"  错误：{exc}")
            return None


async def async_main():
    parser = argparse.ArgumentParser(
        description="遍历目标目录下所有 SKILL.md，调用 OpenAI 兼容接口做技能审核与场景分类"
    )
    parser.add_argument("--target_dir", default=None, help="扫描目录，不传时从 baseline_using.yaml 的 skill_reviewer_config.target_dir 读取")
    parser.add_argument("--concurrency", type=int, default=None, help="并发数，不传时从 baseline_using.yaml 的 pipeline_config.MAX_LLM_CALLS 读取")
    parser.add_argument("--output", default=None, help="输出 JSON 路径，不传时从 baseline_using.yaml 的 skill_reviewer_config.output 读取")
    args = parser.parse_args()

    api_cfg, pipeline_cfg, reviewer_cfg = _load_runtime_config()
    target_dir = _resolve_config_path(args.target_dir or reviewer_cfg.get("target_dir"))
    concurrency = args.concurrency or pipeline_cfg.get("MAX_LLM_CALLS", 50)
    output_path = _resolve_config_path(args.output if args.output is not None else reviewer_cfg.get("output"))

    if not target_dir:
        print("错误：缺少 target_dir，请在 baseline_using.yaml 的 skill_reviewer_config 中配置 target_dir")
        return

    target_dir = os.path.abspath(target_dir)
    if not os.path.isdir(target_dir):
        print(f"错误：目标目录不存在：{target_dir}")
        return

    client, model = _build_client(api_cfg)

    try:
        skill_files = find_skill_files(target_dir)
        if not skill_files:
            print(f"在 {target_dir} 下未找到任何 SKILL.md 文件")
            return

        total = len(skill_files)
        print(f"共找到 {total} 个 SKILL.md 文件，并发数：{concurrency}，开始审核...\n")

        sem = asyncio.Semaphore(concurrency)
        tasks = [
            process_one(sem, client, sf, model, i, total)
            for i, sf in enumerate(skill_files, 1)
        ]
        raw_results = await asyncio.gather(*tasks)
        results = [item for item in raw_results if item is not None]

        print(f"\n审核完成，共处理 {len(results)} 个技能文件。")

        output_json = json.dumps(results, ensure_ascii=False, indent=2)
        if output_path:
            output_dir = os.path.dirname(output_path)
            if output_dir:
                os.makedirs(output_dir, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(output_json)
            print(f"结果已保存到：{output_path}")
        else:
            print("\n===== 审核结果 =====")
            print(output_json)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(async_main())
