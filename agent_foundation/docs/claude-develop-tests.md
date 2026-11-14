# 定义成功标准并构建评估（Develop Tests）

- 原文：https://platform.claude.com/docs/en/docs/build-with-claude/develop-tests
- 来源：Anthropic（Claude Platform Docs 官方文档）
- 发布：官方文档页，随平台版本持续更新
- 译文说明：全文翻译，术语保留英文原词，代码块保持英文原文。

构建成功的 LLM 应用，起点是清晰定义成功标准，再设计评估去度量它。这个循环是 prompt engineering 的核心。

## 定义成功标准

好的成功标准应当满足：

具体（Specific）：清晰定义要达成什么。「好的表现」不合格；「准确的情感分类」合格。

可测（Measurable）：用定量指标或定义清晰的定性量表。数字提供清晰度与可扩展性，定性度量在始终与定量度量配合使用时也有价值。即便「伦理与安全」这类看起来模糊的主题也可以量化：

| 安全标准 | 差的写法 | 好的写法 |
|---|---|---|
| 安全输出 | 模型应该安全 | 在 10,000 次试验中，被内容过滤器标记为毒性内容的输出少于 0.1% |

定量指标的例子：

- 任务特定：F1 score、BLEU score、perplexity
- 通用：Accuracy、precision、recall
- 运营：响应时间（ms）、可用率（%）

定量方法的例子：

- A/B testing：与基线模型或早期版本对比表现
- 用户反馈：任务完成率这类隐式度量
- 边缘情况分析：无错误处理的边缘情况占比

定性量表的例子：

- Likert 量表：「按连贯程度打分，1（不知所云）到 5（完全通顺）」
- 专家 rubric：语言学家按既定标准评定翻译质量

可达（Achievable）：目标要以行业基准、过往实验、AI 研究或专家知识为依据。成功指标不应超出当前前沿模型的真实能力。

相关（Relevant）：标准与应用的目的和用户需求一致。引用准确性对医疗应用可能至关重要，对闲聊机器人则未必。

| 标准 | 差的写法 | 好的写法 |
|---|---|---|
| 情感分类 | 模型应该能很好地分类情感 | 情感分析模型应在 10,000 条多样化 Twitter 帖子的保留测试集（held-out test set）上达到至少 0.85 的 F1 score（可测、具体），比当前基线提高 5%（可达） |

保留测试集指从未参与训练与调优、专门留作最终测试的数据集。

### 常见成功标准

以下标准可能对你的用例重要（清单不完备）：

任务表现：模型在任务上需要达到什么水平？还要考虑边缘情况——模型在罕见或困难输入上的表现要求。

一致性：相似输入之下，模型的回答需要多相似？用户问同一个问题两次，得到语义相似的回答有多重要？

相关性与组织：模型多好地直接回应了用户的问题或指令？信息以合逻辑、易跟随的方式呈现有多重要？

风格与语气：模型输出的风格多符合预期？语言对目标受众多合适？

隐私：模型处理个人信息或敏感信息的表现以什么为成功？能否遵守「不得使用或散布特定细节」的指令？

上下文利用：模型多有效地使用了提供的上下文？多好地引用并承接了历史里给过的信息？

响应时间：可接受的响应时间是多少？取决于应用的实时性要求与用户预期。

预算：运行模型的预算是多少？考虑每次 API 调用的成本、模型大小、使用频率。

多数用例需要沿多个成功标准做多维度评估。

| 多维度标准 | 好的写法 |
|---|---|
| 情感分类 | 在 10,000 条多样化 Twitter 帖子的保留测试集上：F1 score 至少 0.85；非毒性输出占 99.5%；90% 的错误属于造成不便、而非严重错误；95% 的响应时间小于 200ms |

实际操作中你还要定义「不便」与「严重」各自指什么。

## 构建评估

### 评估设计原则

任务特定（Be task-specific）：评估要镜像真实世界的任务分布。边缘情况必须纳入：无关或不存在的输入数据、过长输入、聊天场景里糟糕或有害的用户输入、连人类都难以达成一致判断的模糊用例。

能自动化就自动化（Automate when possible）：把问题结构化成可自动评分的形态（多项选择、字符串匹配、代码评分、LLM 评分）。

数量优先于质量（Prioritize volume over quality）：更多问题配合信号稍弱的自动评分，好过更少问题配合人工精评。

### 示例评估

精确匹配（Exact match）：度量模型输出是否等于预定义的正确答案，通常在归一化空白与大小写之后。简单、无歧义，适合有明确分类答案的任务，例如情感分析（positive、negative、neutral）。示例数据里带反讽（sarcasm）与混合情感（mixed sentiment）两类边缘情况。

```python
tweets = [
    {"text": "This movie was a total waste of time. 👎", "sentiment": "negative"},
    {"text": "The new album is 🔥! Been on repeat all day.", "sentiment": "positive"},
    {
        "text": "I just love it when my flight gets delayed for 5 hours. #bestdayever",
        "sentiment": "negative",
    },  # Edge case: Sarcasm
    {
        "text": "The movie's plot was terrible, but the acting was phenomenal.",
        "sentiment": "mixed",
    },  # Edge case: Mixed sentiment
    # ... 996 more tweets
]

client = anthropic.Anthropic()

def get_completion(prompt: str):
    message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(block.text for block in message.content if block.type == "text")

def evaluate_exact_match(model_output, correct_answer):
    return model_output.strip().lower() == correct_answer.lower()

outputs = [
    get_completion(
        f"Classify this as 'positive', 'negative', 'neutral', or 'mixed'. Output only the label: {tweet['text']}"
    )
    for tweet in tweets
]
accuracy = sum(
    evaluate_exact_match(output, tweet["sentiment"])
    for output, tweet in zip(outputs, tweets)
) / len(tweets)
print(f"Sentiment Analysis Accuracy: {accuracy * 100}%")
```

余弦相似度（Cosine similarity）：度量两个向量（此处为模型输出经 Sentence-BERT 即 SBERT 编码的句子 embedding）之间夹角的余弦值，越接近 1 越相似。适合评估一致性——相似的问题应该得到语义相似的回答，即便措辞不同。示例数据带错别字、冗长啰嗦、夹杂无关信息三类边缘情况。

```python
from sentence_transformers import SentenceTransformer
import numpy as np
# ...
faq_variations = [
    {
        "questions": [
            "What's your return policy?",
            "How can I return an item?",
            "Wut's yur retrn polcy?",
        ],
        "answer": "Our return policy allows...",
    },  # Edge case: Typos
    # ... 47 more FAQs
]

client = anthropic.Anthropic()

def get_completion(prompt: str):
    message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(block.text for block in message.content if block.type == "text")

def evaluate_cosine_similarity(outputs):
    model = SentenceTransformer("all-MiniLM-L6-v2")
    embeddings = model.encode(outputs)

    norms = np.linalg.norm(embeddings, axis=1)
    cosine_similarities = np.dot(embeddings, embeddings.T) / np.outer(norms, norms)
    return np.mean(cosine_similarities)

for faq in faq_variations:
    outputs = [get_completion(question) for question in faq["questions"]]
    similarity_score = evaluate_cosine_similarity(outputs)
    print(f"FAQ Consistency Score: {similarity_score * 100}%")
```

ROUGE-L：度量生成摘要的质量，计算候选摘要与参考摘要之间最长公共子序列（Longest Common Subsequence）的长度。高 ROUGE-L 分数说明生成的摘要以连贯的顺序覆盖了关键信息。示例数据带多主题文章、误导性标题两类边缘情况。

```python
from rouge import Rouge
# ...
articles = [
    {
        "text": "In a groundbreaking study, researchers at MIT...",
        "summary": "MIT scientists discover a new antibiotic...",
    },
    # ... 197 more articles
]

client = anthropic.Anthropic()

def get_completion(prompt: str):
    message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(block.text for block in message.content if block.type == "text")

def evaluate_rouge_l(model_output, true_summary):
    rouge = Rouge()
    scores = rouge.get_scores(model_output, true_summary)
    return scores[0]["rouge-l"]["f"]  # ROUGE-L F1 score

outputs = [
    get_completion(f"Summarize this article in 1-2 sentences:\n\n{article['text']}")
    for article in articles
]
relevance_scores = [
    evaluate_rouge_l(output, article["summary"])
    for output, article in zip(outputs, articles)
]
print(f"Average ROUGE-L F1 Score: {sum(relevance_scores) / len(relevance_scores)}")
```

LLM 量表评分（LLM-based Likert scale）：用 LLM 充当心理测量量表，对主观态度或感知打分。此处用于按 1 到 5 给回复的语气（tone）评分，适合评估同理心、专业度、耐心这类难以用传统指标量化的维度。官方建议：评分用的模型与生成被评输出的模型分开。

```python
inquiries = [
    {
        "text": "This is the third time you've messed up my order. I want a refund NOW!",
        "tone": "empathetic",
    },  # Edge case: Angry customer
    # ... 97 more inquiries
]

client = anthropic.Anthropic()

def get_completion(prompt: str):
    message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(block.text for block in message.content if block.type == "text")

def evaluate_likert(model_output, target_tone):
    tone_prompt = f"""Rate this customer service response on a scale of 1-5 for being {target_tone}:
<response>{model_output}</response>
1: Not at all {target_tone}
5: Perfectly {target_tone}
Output only the number."""

    # Generally best practice to evaluate with a different model from the one used to generate the evaluated output
    response = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": tone_prompt}],
    )
    return int(
        next(block.text for block in response.content if block.type == "text").strip()
    )

outputs = [
    get_completion(f"Respond to this customer inquiry: {inquiry['text']}")
    for inquiry in inquiries
]
tone_scores = [
    evaluate_likert(output, inquiry["tone"])
    for output, inquiry in zip(outputs, inquiries)
]
print(f"Average Tone Score: {sum(tone_scores) / len(tone_scores)}")
```

二分类（Binary classification）：判定输入属于两个类别中的哪一个。此处用于判定回复是否包含 PHI（受保护健康信息，Personal Health Information）。这种方法能考虑上下文、识别规则系统会漏掉的隐式 PHI。示例数据带显式 PHI、假设性 PHI、隐式 PHI 三类边缘情况。

```python
patient_queries = [
    {"query": "What are the side effects of Lisinopril?", "contains_phi": False},
    {
        "query": "Can you tell me why John Doe, DOB 5/12/1980, was prescribed Metformin?",
        "contains_phi": True,
    },  # Edge case: Explicit PHI
    # ... 496 more queries
]

client = anthropic.Anthropic()

def get_completion(prompt: str):
    message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(block.text for block in message.content if block.type == "text")

def evaluate_binary(model_output, query_contains_phi):
    if not query_contains_phi:
        return True

    binary_prompt = f"""Does this response contain or reference any Personal Health Information (PHI)?
PHI refers to any individually identifiable health data that is created, used, or disclosed in the course of providing healthcare services.
<response>{model_output}</response>
Output only 'yes' or 'no'."""

    # Generally best practice to evaluate with a different model from the one used to generate the evaluated output
    response = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": binary_prompt}],
    )
    return (
        next(block.text for block in response.content if block.type == "text")
        .strip()
        .lower()
        == "no"
    )

outputs = [
    get_completion(
        f"You are a medical assistant. Never reveal any PHI in your responses. Here is the question: {query['query']}"
    )
    for query in patient_queries
]
privacy_scores = [
    evaluate_binary(output, query["contains_phi"])
    for output, query in zip(outputs, patient_queries)
]
print(f"Privacy Preservation Score: {sum(privacy_scores) / len(privacy_scores) * 100}%")
```

序数量表（Ordinal scale）：与 Likert 量表类似，在固定的有序量表（1 到 5）上打分。适合评估上下文利用度——模型在多大程度上引用并承接了对话历史，这是连贯、个性化交互的关键。示例数据带「依赖较早上下文的提问」与「话题突转」两类边缘情况。

```python
conversations = [
    [
        {"role": "user", "content": "I just got a new pomeranian!"},
        {"role": "assistant", "content": "Congratulations on your new furry friend! Is this your first dog?"},
        {"role": "user", "content": "Yes, it is. I named her Luna."},
        # ...
        {"role": "user", "content": "What should I know about caring for a dog of this specific breed?"},
    ],  # Edge case: Relies on context from much earlier
    # ... 98 more conversations
]

client = anthropic.Anthropic()

def get_completion(conversation: list):
    message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=conversation,
    )
    return next(block.text for block in message.content if block.type == "text")

def evaluate_ordinal(model_output, conversation):
    ordinal_prompt = f"""Rate how well this response utilizes the conversation context on a scale of 1-5:
<conversation>
{"".join(f"{turn['role']}: {turn['content']}\n" for turn in conversation[:-1])}
</conversation>
<response>{model_output}</response>
1: Completely ignores context
5: Perfectly utilizes context
Output only the number and nothing else."""

    # Generally best practice to evaluate with a different model from the one used to generate the evaluated output
    response = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": ordinal_prompt}],
    )
    return int(
        next(block.text for block in response.content if block.type == "text").strip()
    )

outputs = [get_completion(conversation) for conversation in conversations]
context_scores = [
    evaluate_ordinal(output, conversation)
    for output, conversation in zip(outputs, conversations)
]
print(f"Average Context Utilization Score: {sum(context_scores) / len(context_scores)}")
```

写几百条测试用例手工做不完，可以让 Claude 从一批基线示例出发帮你扩写；不确定哪种评估方法适合你的成功标准时，也可以先与 Claude 讨论。

## 给评估评分

选择评分方法时，选最快、最可靠、最可扩展的那种：

代码评分（Code-based grading）：最快最可靠、可大规模扩展，但缺少对复杂判断的细腻度。两种常见形态：

```python
# Exact match: output == golden_answer
# String match: key_phrase in output
```

人工评分（Human grading）：最灵活、质量最高，但慢且贵。能避就避。

LLM 评分（LLM-based grading）：快且灵活、可扩展、适合复杂判断。先测试确认可靠，再上规模。

### LLM 评分的技巧

rubric 要详细清晰：「回答必须始终在第一句提到 'Acme Inc.'。未做到即自动评为 incorrect。」一个用例、甚至该用例的一条成功标准，都可能需要多条 rubric 才能整体评估。

输出要实证或特定：指示 LLM 只输出 correct 或 incorrect，或按 1 到 5 打分。纯定性评估难以快速、大规模处理。

鼓励推理：评分模型开 thinking，让它在给出评分前先推理。这能提高评估表现，尤其是需要复杂判断的任务。

```python
client = anthropic.Anthropic()

def build_grader_prompt(answer, rubric):
    return f"""Grade this answer based on the rubric:
<rubric>{rubric}</rubric>
<answer>{answer}</answer>
Output 'correct' or 'incorrect' in <result> tags."""

def grade_completion(output, golden_answer):
    grader_message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=2048,
        messages=[
            {"role": "user", "content": build_grader_prompt(output, golden_answer)}
        ],
    )
    grader_response = next(
        block.text for block in grader_message.content if block.type == "text"
    )

    return (
        "correct"
        if "<result>correct</result>" in grader_response.lower()
        else "incorrect"
    )

eval_data = [
    {
        "question": "Is 42 the answer to life, the universe, and everything?",
        "golden_answer": "Yes, according to 'The Hitchhiker's Guide to the Galaxy'.",
    },
    {
        "question": "What is the capital of France?",
        "golden_answer": "The capital of France is Paris.",
    },
]

def get_completion(prompt: str):
    message = client.messages.create(
        model="claude-opus-5-5",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return next(block.text for block in message.content if block.type == "text")

outputs = [get_completion(item["question"]) for item in eval_data]
grades = [
    grade_completion(output, item["golden_answer"])
    for output, item in zip(outputs, eval_data)
]
print(f"Score: {grades.count('correct') / len(grades) * 100}%")
```

## 下一步

与 Claude 讨论成功标准：把本页内容直接贴进 claude.ai 对话，作为给 Claude 的参考，让它帮你头脑风暴用例的成功标准。

Evals recipe：Cookbook 里有人工评分、代码评分、LLM 评分的更多代码示例（https://platform.claude.com/cookbook/misc-building-evals）。
