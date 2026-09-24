// Developer-only asset recipe. This is the original laptop reflection room, unchanged.
// Run bakeRoom(canvas) in a local Three-enabled browser, gzip result.result, and save as
// public/models/laptop-room.dat. Never imported into the production application.
import { ACESFilmicToneMapping, BackSide, BoxGeometry, Mesh, MeshBasicMaterial, PlaneGeometry, PMREMGenerator, Scene, SRGBColorSpace, WebGLRenderer } from "three"

function darkRoom(): Scene {
  const room = new Scene()
  room.add(
    new Mesh(
      new BoxGeometry(14, 14, 14),
      new MeshBasicMaterial({ color: 0x07070d, side: BackSide }),
    ),
  )

  const strip = (x: number, y: number, z: number, w: number, h: number, colour: number, gain: number) => {
    const material = new MeshBasicMaterial({ color: colour })
    material.color.multiplyScalar(gain)
    const panel = new Mesh(new PlaneGeometry(w, h), material)
    panel.position.set(x, y, z)
    panel.lookAt(0, 0, 0)
    room.add(panel)
  }

  strip(0, 6, 1.5, 9, 4, 0xe8eefb, 2.1) // the soft box above
  strip(-5.5, 1.5, -3, 5, 6, 0x6a5fae, 1.5) // indigo behind left
  strip(5, 0.5, -3.5, 4, 5, 0x49b9c6, 0.9) // cyan behind right
  return room
}


export function bakeRoom(canvas: HTMLCanvasElement) {
 const renderer = new WebGLRenderer({canvas,antialias:true,alpha:true})
 renderer.outputColorSpace=SRGBColorSpace;renderer.toneMapping=ACESFilmicToneMapping;renderer.toneMappingExposure=1
 const generator=new PMREMGenerator(renderer), room=darkRoom(), target=generator.fromScene(room,.05)
 const pixels=new Uint16Array(target.width*target.height*4)
 renderer.readRenderTargetPixels(target,0,0,target.width,target.height,pixels)
 const header=new Uint32Array([target.width,target.height])
 const result=new Uint8Array(8+pixels.byteLength);result.set(new Uint8Array(header.buffer));result.set(new Uint8Array(pixels.buffer),8)
 room.traverse(child => { if (child instanceof Mesh) { child.geometry.dispose(); (child.material as MeshBasicMaterial).dispose() } })
 target.dispose();generator.dispose();renderer.dispose()
 return {result,width:target.width,height:target.height}
}
