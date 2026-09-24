/**
 * Test doubles for the Web Speech APIs, which jsdom does not implement.
 *
 * These deliberately do *not* auto-fire lifecycle events: each test drives the exact sequence
 * it wants to assert on (start-then-error, end-without-start, and so on), which is the whole
 * point given the bug being covered was about event ordering.
 */

interface RecognitionHandlers {
  onstart: (() => void) | null
  onerror: ((event: { error: string; message?: string }) => void) | null
  onend: (() => void) | null
  onresult: ((event: unknown) => void) | null
}

export class FakeSpeechRecognition implements RecognitionHandlers {
  static instances: FakeSpeechRecognition[] = []

  static reset() {
    FakeSpeechRecognition.instances = []
  }

  static latest(): FakeSpeechRecognition {
    const instance = FakeSpeechRecognition.instances.at(-1)
    if (!instance) throw new Error("No FakeSpeechRecognition was constructed")
    return instance
  }

  continuous = false
  interimResults = false
  maxAlternatives = 0
  lang = ""

  onstart: (() => void) | null = null
  onerror: ((event: { error: string; message?: string }) => void) | null = null
  onend: (() => void) | null = null
  onresult: ((event: unknown) => void) | null = null
  onaudiostart: (() => void) | null = null
  onaudioend: (() => void) | null = null
  onsoundstart: (() => void) | null = null
  onsoundend: (() => void) | null = null
  onspeechstart: (() => void) | null = null
  onspeechend: (() => void) | null = null
  onnomatch: (() => void) | null = null

  startCalls = 0
  stopCalls = 0
  abortCalls = 0
  /** Set to make `start()` throw, mimicking Chrome's InvalidStateError. */
  throwOnStart: Error | null = null

  constructor() {
    FakeSpeechRecognition.instances.push(this)
  }

  start() {
    this.startCalls += 1
    if (this.throwOnStart) throw this.throwOnStart
  }

  stop() {
    this.stopCalls += 1
  }

  abort() {
    this.abortCalls += 1
  }

  /* --- test drivers --- */
  fireStart() {
    this.onstart?.()
  }

  fireError(code: string) {
    this.onerror?.({ error: code, message: "" })
  }

  fireEnd() {
    this.onend?.()
  }

  fireResult(transcript: string, isFinal: boolean) {
    this.onresult?.({
      resultIndex: 0,
      results: { length: 1, 0: { isFinal, 0: { transcript } } },
    })
  }
}

export function installFakeRecognition() {
  FakeSpeechRecognition.reset()
  Object.defineProperty(window, "SpeechRecognition", {
    value: FakeSpeechRecognition,
    configurable: true,
    writable: true,
  })
  Object.defineProperty(window, "webkitSpeechRecognition", {
    value: FakeSpeechRecognition,
    configurable: true,
    writable: true,
  })
}

export function uninstallFakeRecognition() {
  Reflect.deleteProperty(window, "SpeechRecognition")
  Reflect.deleteProperty(window, "webkitSpeechRecognition")
}

/* --- Speech synthesis ------------------------------------------------------------------- */

export class FakeUtterance {
  lang = ""
  rate = 1
  pitch = 1
  voice: SpeechSynthesisVoice | null = null
  onstart: (() => void) | null = null
  onend: (() => void) | null = null
  onerror: (() => void) | null = null
  onboundary: (() => void) | null = null
  text: string

  constructor(text: string) {
    this.text = text
  }
}

export function makeVoice(
  name: string,
  lang: string,
  options: { localService?: boolean; default?: boolean } = {},
): SpeechSynthesisVoice {
  return {
    name,
    lang,
    localService: options.localService ?? true,
    default: options.default ?? false,
    voiceURI: name,
  } as SpeechSynthesisVoice
}

export class FakeSpeechSynthesis {
  spoken: FakeUtterance[] = []
  cancelCalls = 0
  private listeners: Array<() => void> = []
  private voices: SpeechSynthesisVoice[]

  constructor(voices: SpeechSynthesisVoice[] = []) {
    this.voices = voices
  }

  getVoices() {
    return this.voices
  }

  /** Mimics Chrome populating the list asynchronously and firing `voiceschanged`. */
  setVoicesLater(voices: SpeechSynthesisVoice[]) {
    this.voices = voices
    this.listeners.forEach((listener) => listener())
  }

  speak(utterance: FakeUtterance) {
    this.spoken.push(utterance)
  }

  cancel() {
    this.cancelCalls += 1
  }

  addEventListener(_type: string, listener: () => void) {
    this.listeners.push(listener)
  }

  removeEventListener(_type: string, listener: () => void) {
    this.listeners = this.listeners.filter((item) => item !== listener)
  }
}

export function installFakeSynthesis(voices: SpeechSynthesisVoice[]): FakeSpeechSynthesis {
  const synth = new FakeSpeechSynthesis(voices)
  Object.defineProperty(window, "speechSynthesis", {
    value: synth,
    configurable: true,
    writable: true,
  })
  Object.defineProperty(globalThis, "SpeechSynthesisUtterance", {
    value: FakeUtterance,
    configurable: true,
    writable: true,
  })
  return synth
}
