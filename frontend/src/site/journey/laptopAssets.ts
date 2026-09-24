export interface LaptopAssets {
  model: ArrayBuffer
  room: ArrayBuffer
  modelMs: number
  roomMs: number
}
let cached: Promise<LaptopAssets> | undefined

/** One session cache of immutable source data, never a live WebGL context. */
export function loadLaptopAssets(): Promise<LaptopAssets> {
  if (!cached) {
    const started = performance.now()
    const model = fetch("/models/laptop.glb").then(async response => {
      if (!response.ok) throw Error("Laptop model unavailable")
      const buffer = await response.arrayBuffer()
      return { buffer, ms: performance.now() - started }
    }).catch(error => { throw new Error("Model: " + String(error)) })
    const room = fetch("/models/laptop-room.dat").then(async response => {
      if (!response.ok || !response.body) throw Error("Laptop reflections unavailable")
      const buffer = await new Response(response.body.pipeThrough(new DecompressionStream("gzip"))).arrayBuffer()
      return { buffer, ms: performance.now() - started }
    }).catch(error => { throw new Error("Reflections: " + String(error)) })
    cached = Promise.all([model, room]).then(([model, room]) => ({ model: model.buffer, room: room.buffer, modelMs: model.ms, roomMs: room.ms }))
      .catch(error => { cached = undefined; throw error })
  }
  return cached
}

