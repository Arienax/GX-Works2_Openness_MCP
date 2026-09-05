import argparse
import base64
import json
from pathlib import Path
import re
import time
from urllib.request import urlopen

import websocket


DEBUG_ENDPOINT = "http://127.0.0.1:9222/json/list"


class CDPClient:
    def __init__(self):
        targets = json.load(urlopen(DEBUG_ENDPOINT, timeout=5))
        page = next(
            item
            for item in targets
            if item.get("type") == "page" and "kl.zjwison.cn" in item.get("url", "")
        )
        self.ws = websocket.create_connection(
            page["webSocketDebuggerUrl"],
            suppress_origin=True,
            timeout=15,
        )
        self.next_id = 1

    def close(self):
        self.ws.close()

    def call(self, method, params=None):
        message_id = self.next_id
        self.next_id += 1
        self.ws.send(
            json.dumps(
                {"id": message_id, "method": method, "params": params or {}},
                ensure_ascii=False,
            )
        )
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == message_id:
                if "error" in message:
                    raise RuntimeError(message["error"])
                return message.get("result", {})

    def evaluate(self, expression):
        result = self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "returnByValue": True,
                "awaitPromise": True,
            },
        )
        remote = result.get("result", {})
        if remote.get("subtype") == "error":
            raise RuntimeError(remote.get("description", "JavaScript evaluation failed"))
        return remote.get("value")


def inspect_question(client):
    expression = r"""
(() => {
  const index = document.querySelector('.index');
  if (!index) return null;
  return {
    index: index.outerHTML,
    parent: index.parentElement.outerHTML.slice(0, 12000),
    grandparent: index.parentElement.parentElement.outerHTML.slice(0, 20000)
  };
})()
"""
    print(json.dumps(client.evaluate(expression), ensure_ascii=False, indent=2))


EXTRACT_EXPRESSION = r"""
(() => Array.from(document.querySelectorAll('.questions-item')).map(item => {
  const optionNodes = Array.from(item.querySelectorAll('.option-list input'));
  const options = optionNodes.map(input => {
    const label = item.querySelector(`label[for="${input.id}"]`);
    const text = (label?.getAttribute('title') || label?.innerText || '').trim();
    return {key: input.value, text};
  });
  const indexText = (item.querySelector('.index')?.innerText || '').trim();
  const numberMatch = indexText.match(/第\s*(\d+)\s*题/);
  const isJudgment = options.length === 2 &&
    options[0]?.text === '对' && options[1]?.text === '错';
  const inputType = optionNodes[0]?.type || '';
  return {
    number: numberMatch ? Number(numberMatch[1]) : null,
    question_id: item.getAttribute('questionid') || '',
    type: isJudgment ? '判断题' : (inputType === 'checkbox' ? '多选题' : '单选题'),
    stem: (item.querySelector('.content')?.innerText || '').trim(),
    options,
    answer: (item.getAttribute('rightkey') || item.querySelector('.res')?.innerText || '').trim(),
    images: Array.from(item.querySelectorAll('img')).map(img => img.src).filter(Boolean)
  };
}))()
"""


def format_text(questions):
    lines = [f"在线题库题目与答案（共 {len(questions)} 题）", "=" * 48, ""]
    current_type = None
    for question in questions:
        if question["type"] != current_type:
            current_type = question["type"]
            lines.extend([current_type, "-" * 24])
        lines.append(f"第{question['number']}题：{question['stem']}")
        for option in question["options"]:
            lines.append(f"{option['key']}：{option['text']}")
        answer_text = []
        option_map = {item["key"]: item["text"] for item in question["options"]}
        for key in question["answer"]:
            if key in option_map:
                answer_text.append(f"{key}（{option_map[key]}）")
            else:
                answer_text.append(key)
        lines.append("答案：" + "、".join(answer_text))
        if question.get("images"):
            lines.append("图片：" + "；".join(question["images"]))
        lines.append("")
    return "\n".join(lines)


def save_results(questions, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "题库_原始数据.json"
    text_path = output_dir / "题库_题目与答案.txt"
    json_path.write_text(
        json.dumps(questions, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    text_path.write_text(format_text(questions), encoding="utf-8")
    return json_path, text_path


def scrape_all(client, output_dir):
    questions_by_number = {}
    page = 1
    while True:
        questions = client.evaluate(EXTRACT_EXPRESSION) or []
        if not questions:
            raise RuntimeError(f"第 {page} 页没有识别到题目")
        first_number = questions[0]["number"]
        last_number = questions[-1]["number"]
        for question in questions:
            questions_by_number[question["number"]] = question
        ordered = [questions_by_number[key] for key in sorted(questions_by_number)]
        save_results(ordered, output_dir)
        print(
            f"page={page} range={first_number}-{last_number} "
            f"page_count={len(questions)} total={len(ordered)}",
            flush=True,
        )
        if len(ordered) >= 515:
            break

        next_state = client.evaluate(
            r"""
(() => {
  const button = Array.from(document.querySelectorAll('button,input[type=button],a'))
    .find(node => (node.innerText || node.value || '').trim() === '下一页试题');
  if (!button || button.disabled) return false;
  button.click();
  return true;
})()
"""
        )
        if not next_state:
            break

        deadline = time.time() + 25
        changed = False
        while time.time() < deadline:
            time.sleep(0.8)
            try:
                next_first = client.evaluate(
                    "Number((document.querySelector('.index')?.innerText || '').match(/\\d+/)?.[0] || 0)"
                )
            except Exception:
                continue
            if next_first and next_first != first_number:
                changed = True
                break
        if not changed:
            raise RuntimeError(f"点击下一页后题目未更新，当前已保存 {len(ordered)} 题")
        page += 1

    ordered = [questions_by_number[key] for key in sorted(questions_by_number)]
    paths = save_results(ordered, output_dir)
    return ordered, paths


def materialize_images(output_dir):
    json_path = output_dir / "题库_原始数据.json"
    questions = json.loads(json_path.read_text(encoding="utf-8"))
    image_dir = output_dir / "图片"
    image_dir.mkdir(parents=True, exist_ok=True)
    saved = 0
    for question in questions:
        local_images = []
        for index, source in enumerate(question.get("images", []), 1):
            match = re.match(r"data:image/([^;]+);base64,(.*)", source, re.S)
            if not match:
                local_images.append(source)
                continue
            extension = "jpg" if match.group(1) in {"jpeg", "jpg"} else match.group(1)
            filename = f"第{question['number']}题_{index}.{extension}"
            (image_dir / filename).write_bytes(base64.b64decode(match.group(2)))
            local_images.append(f"图片/{filename}")
            saved += 1
        question["images"] = local_images
    save_results(questions, output_dir)
    return saved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inspect", "scrape", "materialize"])
    parser.add_argument("--output-dir", default="题库复习资料")
    args = parser.parse_args()
    if args.command == "materialize":
        print(f"saved_images={materialize_images(Path(args.output_dir))}")
        return
    client = CDPClient()
    try:
        if args.command == "inspect":
            inspect_question(client)
        elif args.command == "scrape":
            questions, paths = scrape_all(client, Path(args.output_dir))
            print(f"saved={len(questions)} json={paths[0]} text={paths[1]}")
    finally:
        client.close()


if __name__ == "__main__":
    main()
