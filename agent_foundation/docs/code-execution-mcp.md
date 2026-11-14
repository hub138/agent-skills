# 用 MCP 做代码执行：构建更高效的 agent（Code execution with MCP: Building more efficient agents）

- 原文：[Code execution with MCP: Building more efficient agents](https://www.anthropic.com/research/code-execution-with-mcp)
- 来源：Anthropic Engineering，作者 Adam Jones 与 Conor Kelly
- 发布：2025-11-04
- 译文说明：全文翻译，术语保留英文原词；图片为原文插图，地址为原文 CDN 直链；代码示例保留英文原样。

[Model Context Protocol（MCP）](https://modelcontextprotocol.io/)是连接 AI agent 与外部系统的开放标准。过去把 agent 接到工具和数据上，每一对组合都要写一套定制集成，造成碎片化与重复劳动，真正互联的系统难以规模化。MCP 提供了通用协议：开发者在自己的 agent 里实现一次 MCP，就接通了整个集成生态。

MCP 自 2024 年 11 月发布以来普及很快：社区建起了数以千计的 [MCP server](https://github.com/modelcontextprotocol/servers)，所有主流编程语言都有 [SDK](https://modelcontextprotocol.io/docs/sdk)，业界已把 MCP 当作连接 agent 与工具和数据的事实标准。

如今开发者构建的 agent 常常横跨几十个 MCP server、接入成百上千个工具。但随着接入的工具越来越多，把全部工具定义预先加载进上下文、让中间结果穿过上下文窗口传递，会拖慢 agent 并抬高成本。

本文探讨代码执行如何让 agent 更高效地与 MCP server 交互：用更少的 token 处理更多的工具。

## 工具造成的过度 token 消耗让 agent 变得低效

MCP 用量上去之后，有两种常见形态会推高 agent 的成本与延迟：

1. 工具定义让上下文窗口过载；
2. 中间工具结果消耗额外 token。

### 1. 工具定义让上下文窗口过载

多数 MCP client 把全部工具定义预先加载进上下文，用直接工具调用语法暴露给模型。这些工具定义长这样：

```
gdrive.getDocument
     Description: Retrieves a document from Google Drive
     Parameters:
                documentId (required, string): The ID of the document to retrieve
                fields (optional, string): Specific fields to return
     Returns: Document object with title, body content, metadata, permissions, etc.
```

```
salesforce.updateRecord
    Description: Updates a record in Salesforce
    Parameters:
               objectType (required, string): Type of Salesforce object (Lead, Contact,      Account, etc.)
               recordId (required, string): The ID of the record to update
               data (required, object): Fields to update with their new values
     Returns: Updated record object with confirmation
```

工具描述占用更多上下文窗口空间，响应时间与成本随之上升。agent 接入几千个工具时，读完一条请求之前就要先处理几十万 token。

### 2. 中间工具结果消耗额外 token

多数 MCP client 允许模型直接调用 MCP 工具。比如你对 agent 说：「从 Google Drive 下载我的会议记录，附到 Salesforce 的这条潜在客户（Lead）上。」

模型会这样调用：

```
TOOL CALL: gdrive.getDocument(documentId: "abc123")
        → returns "Discussed Q4 goals...\n[full transcript text]"
           (loaded into model context)

TOOL CALL: salesforce.updateRecord(
			objectType: "SalesMeeting",
			recordId: "00Q5f000001abcXYZ",
  			data: { "Notes": "Discussed Q4 goals...\n[full transcript text written out]" }
		)
		(model needs to write entire transcript into context again)
```

每个中间结果都必须过一遍模型。这个例子里，完整的会议记录流经模型两次。一场 2 小时的销售会议，可能意味着额外处理 50,000 token。更大的文档可能超出上下文窗口上限，工作流直接中断。

文档大、数据结构复杂时，模型在工具调用之间复制数据也更容易出错。

![MCP 客户端与消息循环示意图](https://www-cdn.anthropic.com/images/4zrzovbb/website/9ecf165020005c09a22a9472cee6309555485619-1920x1080.png)

## 用 MCP 做代码执行，改善上下文效率

代码执行环境在 agent 里越来越普及，一种解法是把 MCP server 呈现为代码 API，让 agent 写代码去调用。这一思路同时解决两个问题：agent 可以只加载需要的工具，也可以先在执行环境里处理数据，再把结果传回模型。

实现方式不止一种。一种做法是为接入的全部 MCP server 生成一棵工具文件树。下面是一个 TypeScript 实现：

```
servers
├── google-drive
│   ├── getDocument.ts
│   ├── ... (other tools)
│   └── index.ts
├── salesforce
│   ├── updateRecord.ts
│   ├── ... (other tools)
│   └── index.ts
└── ... (other servers)
```

每个工具对应一个文件，长这样：

```
// ./servers/google-drive/getDocument.ts
import { callMCPTool } from "../../../client.js";

interface GetDocumentInput {
  documentId: string;
}

interface GetDocumentResponse {
  content: string;
}

/* Read a document from Google Drive */
export async function getDocument(input: GetDocumentInput): Promise<GetDocumentResponse> {
  return callMCPTool<GetDocumentResponse>('google_drive__get_document', input);
}
```

前面的 Google Drive 到 Salesforce 例子，此时变成这段代码：

```
// Read transcript from Google Docs and add to Salesforce prospect
import * as gdrive from './servers/google-drive';
import * as salesforce from './servers/salesforce';

const transcript = (await gdrive.getDocument({ documentId: 'abc123' })).content;
await salesforce.updateRecord({
  objectType: 'SalesMeeting',
  recordId: '00Q5f000001abcXYZ',
  data: { Notes: transcript }
});
```

agent 通过探索文件系统发现工具：列出 `./servers/` 目录找到可用的 server（如 `google-drive` 与 `salesforce`），再读它需要的具体工具文件（如 `getDocument.ts` 与 `updateRecord.ts`）来理解每个工具的接口。这样 agent 只加载当前任务需要的定义，token 用量从 150,000 降到 2,000，时间与成本节省 98.7%。

Cloudflare [发布过类似发现](https://blog.cloudflare.com/code-mode/)，把 MCP 上的代码执行称为 "Code Mode"。核心洞见相同：LLM 擅长写代码，开发者应当利用这个长处，构建与 MCP server 交互更高效的 agent。

## MCP 代码执行的好处

MCP 代码执行让 agent 更高效地使用上下文：按需加载工具、数据进模型前先过滤、单步执行复杂逻辑。这个做法还附带安全与状态管理上的收益。

### 渐进式披露

模型非常擅长在文件系统里导航。把工具呈现为文件系统上的代码，模型就能按需读取工具定义，无需预先读入全部。

也可以在 server 上加一个 `search_tools` 工具来查找相关定义。比如使用上面假想的 Salesforce server 时，agent 搜索 "salesforce"，只加载当前任务需要的那些工具。给 `search_tools` 加一个详细程度参数，让 agent 自选需要的级别（只要名字、名字加描述、或带 schema 的完整定义），同样能帮 agent 节省上下文、快速找到工具。

### 上下文高效的工具结果

面对大数据集，agent 可以先在代码里过滤与转换结果再返回。设想取一张 10,000 行的表格：

```
// Without code execution - all rows flow through context
TOOL CALL: gdrive.getSheet(sheetId: 'abc123')
        → returns 10,000 rows in context to filter manually

// With code execution - filter in the execution environment
const allRows = await gdrive.getSheet({ sheetId: 'abc123' });
const pendingOrders = allRows.filter(row => 
  row["Status"] === 'pending'
);
console.log(`Found ${pendingOrders.length} pending orders`);
console.log(pendingOrders.slice(0, 5)); // Only log first 5 for review
```

agent 只看到 5 行，其余 9,995 行不进上下文。聚合运算、跨多个数据源的 join、抽取特定字段，同样的模式都适用，全程不撑大上下文窗口。

#### 更强且更省上下文的控制流

循环、条件、错误处理都能用熟悉的代码模式完成，无需把一次次工具调用串成链。比如要在 Slack 里等一条部署通知，agent 可以写：

```
let found = false;
while (!found) {
  const messages = await slack.getChannelHistory({ channel: 'C123456' });
  found = messages.some(m => m.text.includes('deployment complete'));
  if (!found) await new Promise(r => setTimeout(r, 5000));
}
console.log('Deployment notification received');
```

这比在 agent 循环里交替执行 MCP 工具调用与 sleep 命令更高效。

另外，能写出一段会被执行的条件树，还能省下 time to first token（首 token 时间）延迟：if 语句的判断交给代码执行环境，无需等模型逐条评估。

### 保护隐私的操作

agent 使用 MCP 代码执行时，中间结果默认留在执行环境里。agent 只看得到你显式 log 或 return 的内容，不想给模型看的数据可以在工作流里流转，全程不进入模型上下文。

对更敏感的负载，agent harness 还能自动对敏感数据做 tokenization。设想要把电子表格里的客户联系方式导入 Salesforce。agent 写：

```
const sheet = await gdrive.getSheet({ sheetId: 'abc123' });
for (const row of sheet.rows) {
  await salesforce.updateRecord({
    objectType: 'Lead',
    recordId: row.salesforceId,
    data: { 
      Email: row.email,
      Phone: row.phone,
      Name: row.name
    }
  });
}
console.log(`Updated ${sheet.rows.length} leads`);
```

MCP client 拦截数据，在到达模型前把 PII（个人身份信息）替换成占位 token：

```
// What the agent would see, if it logged the sheet.rows:
[
  { salesforceId: '00Q...', email: '[EMAIL_1]', phone: '[PHONE_1]', name: '[NAME_1]' },
  { salesforceId: '00Q...', email: '[EMAIL_2]', phone: '[PHONE_2]', name: '[NAME_2]' },
  ...
]
```

之后数据进入别的 MCP 工具调用时，由 MCP client 查表换回原值。真实的邮箱、电话与姓名从 Google Sheets 流向 Salesforce，但从不经过模型。这避免 agent 意外记录或处理敏感数据，也可以用来定义确定性的安全规则，指定数据能流向哪里、不能流向哪里。

### 状态持久化与 skills

带文件系统访问的代码执行，让 agent 能跨操作维护状态。agent 可以把中间结果写进文件，从而恢复中断的工作、追踪进度：

```
const leads = await salesforce.query({ 
  query: 'SELECT Id, Email FROM Lead LIMIT 1000' 
});
const csvData = leads.map(l => `${l.Id},${l.Email}`).join('\n');
await fs.writeFile('./workspace/leads.csv', csvData);

// Later execution picks up where it left off
const saved = await fs.readFile('./workspace/leads.csv', 'utf-8');
```

agent 还能把自己的代码存成可复用函数。agent 为某个任务写出可用的代码后，可以把实现保存下来供将来使用：

```
// In ./skills/save-sheet-as-csv.ts
import * as gdrive from './servers/google-drive';
export async function saveSheetAsCsv(sheetId: string) {
  const data = await gdrive.getSheet({ sheetId });
  const csv = data.map(row => row.join(',')).join('\n');
  await fs.writeFile(`./workspace/sheet-${sheetId}.csv`, csv);
  return `./workspace/sheet-${sheetId}.csv`;
}

// Later, in any agent execution:
import { saveSheetAsCsv } from './skills/save-sheet-as-csv';
const csvPath = await saveSheetAsCsv('abc123');
```

这与 [Skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) 的概念紧密相关：Skills 是由可复用指令、脚本与资源组成的文件夹，帮助模型在专门任务上做得更好。给这些保存下来的函数加上 SKILL.md 文件，就构成一个结构化的 skill，模型可以引用并使用。假以时日，agent 会攒出一个更高阶能力的工具箱，逐步演化出它高效工作所需的脚手架。

需要注意的是，代码执行也引入自身的复杂度。运行 agent 生成的代码，需要一个带[沙箱隔离](https://www.anthropic.com/engineering/claude-code-sandboxing)、资源限制与监控的安全执行环境。这些基础设施要求带来直接工具调用所没有的运维开销与安全考量。代码执行的收益（更低的 token 成本、更低的延迟、更好的工具组合能力）需要与这些实现成本放在一起权衡。

## 小结

MCP 为 agent 连接大量工具与系统提供了基础协议。但接入的 server 一旦过多，工具定义与结果就会消耗过量 token，拖低 agent 效率。

这里的许多问题看起来很新（上下文管理、工具组合、状态持久化），在软件工程里却都有现成解法。代码执行把这些成熟模式应用到 agent 上，让 agent 用熟悉的编程构造与 MCP server 更高效地交互。如果你实现了这个方案，欢迎把发现分享给 [MCP 社区](https://modelcontextprotocol.io/community/communication)。

## 作者与致谢

本文由 Adam Jones 与 Conor Kelly 撰写。感谢 Jeremy Fox、Jerome Swannack、Stuart Ritchie、Molly Vorwerck、Matt Samuels 与 Maggie Vo 对草稿的反馈。
