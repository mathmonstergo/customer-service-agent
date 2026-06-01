// SSE 流式适配：读 fetch 的 ReadableStream，按行解析 JSON 事件。
// 兼容 admin_server.py 的 /api/assistant/chat-stream 协议：
//   每行一个 JSON：{ event: "meta" | "step" | "delta" | "done" | "error", ... }

export type StreamEvent =
  | { event: 'meta'; [key: string]: unknown }
  | { event: 'step'; name: string; [key: string]: unknown }
  | { event: 'delta'; text: string }
  | { event: 'done'; [key: string]: unknown }
  | { event: 'error'; message: string }

export interface StreamOptions {
  signal?: AbortSignal
  onEvent: (event: StreamEvent) => void
}

export async function streamJsonLines(
  path: string,
  init: RequestInit,
  { signal, onEvent }: StreamOptions,
): Promise<void> {
  const res = await fetch(path, { ...init, signal })
  if (!res.ok || !res.body) {
    const text = await res.text().catch(() => '')
    throw new Error(text || `stream failed: ${res.status}`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let nl = buffer.indexOf('\n')
    while (nl >= 0) {
      const line = buffer.slice(0, nl).trim()
      buffer = buffer.slice(nl + 1)
      if (line) {
        try {
          onEvent(JSON.parse(line) as StreamEvent)
        } catch {
          // 跳过无法解析的行
        }
      }
      nl = buffer.indexOf('\n')
    }
  }
  const tail = buffer.trim()
  if (tail) {
    try {
      onEvent(JSON.parse(tail) as StreamEvent)
    } catch {
      // ignore
    }
  }
}
