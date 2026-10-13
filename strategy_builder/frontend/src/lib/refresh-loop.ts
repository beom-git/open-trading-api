/** Browser-owned sequential polling with generation guards and bounded backoff. */
export class RefreshLoop<T> {
  private timer: ReturnType<typeof setTimeout> | null = null;
  private controller: AbortController | null = null;
  private epoch = 0;
  private busy = false;
  private running = false;
  private visible = true;
  private disposed = false;
  private failures = 0;
  constructor(private load: (signal: AbortSignal) => Promise<T>, private interval: number,
    private result: (value: T) => void, private error: (error: unknown) => void,
    private status: (state: string, nextAt: number | null) => void) {}
  private clear() { if (this.timer !== null) clearTimeout(this.timer); this.timer = null; }
  private schedule(ms: number) {
    this.clear(); if (!this.running || !this.visible || this.disposed) return;
    this.status(this.failures ? "재시도 대기" : "다음 조회 대기", Date.now()+ms);
    this.timer = setTimeout(()=>void this.tick(), ms);
  }
  start() { if (this.disposed || this.running) return; this.running=true;this.failures=0;this.schedule(0); }
  pause() { this.running=false;this.epoch++;this.clear();this.controller?.abort();this.status("일시정지",null); }
  setVisible(visible:boolean) {
    if(this.visible===visible)return;this.visible=visible;this.epoch++;this.clear();this.controller?.abort();
    if(visible)this.schedule(0);else this.status("숨김 탭 · 일시정지",null);
  }
  manual() { if(this.disposed||!this.visible||this.busy)return;this.failures=0;this.clear();void this.tick(true); }
  dispose() { this.pause();this.disposed=true; }
  private async tick(manual=false) {
    if(this.disposed||!this.visible||this.busy||(!this.running&&!manual))return;
    this.busy=true;const epoch=this.epoch;const controller=new AbortController();this.controller=controller;this.status("조회 중",null);
    try{const value=await this.load(controller.signal);if(epoch===this.epoch&&!this.disposed){this.failures=0;this.result(value);}}
    catch(e){if(epoch===this.epoch&&!this.disposed){this.failures++;this.error(e);}}
    finally{
      this.busy=false;this.controller=null;
      if(this.disposed)return;
      if(epoch!==this.epoch){this.schedule(0);return;}
      if(this.failures>=5){this.running=false;this.status("장애 · 자동 갱신 중지 (수동 확인 필요)",null);return;}
      if(this.running)this.schedule(Math.min(300000,this.interval*2**Math.min(this.failures,4)));
      else this.status("일시정지",null);
    }
  }
}
export function signalIsNew(previous:string|undefined,current:string){return !!previous&&previous!==current;}
