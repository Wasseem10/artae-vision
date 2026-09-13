// Local-only browser smoke test for the production clip extractor; no cloud upload.
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
const require = createRequire(new URL("../apps/web/package.json", import.meta.url));
const ts = require("typescript");
const source = readFileSync(new URL("../apps/web/src/lib/event-clip.ts", import.meta.url), "utf8");
const compiled = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText;
const sample = readFileSync(new URL("../apps/web/public/vision/samples/fall-forward.mp4", import.meta.url));
const html = `<!doctype html><html><body style="font:18px system-ui;padding:32px"><h1>Local event-clip test</h1><p>No cloud upload or alert is sent.</p><button id="run">Prepare test clip</button><pre id="result">Ready</pre><video id="clip" controls style="width:640px;max-width:100%"></video><script type="module">
import {extractEventClip} from '/extract.js';
document.querySelector('#run').onclick=async()=>{
 const result=document.querySelector('#result'); result.textContent='Encoding real video…';
 try {const clip=await extractEventClip('/sample.mp4',5,new AbortController().signal);
 const video=document.querySelector('#clip');video.src=URL.createObjectURL(clip.blob);
 result.textContent=JSON.stringify({bytes:clip.blob.size,type:clip.blob.type,start:clip.start,duration:clip.duration,width:clip.width,height:clip.height},null,2);
 video.onloadeddata=()=>{result.textContent+='\\nPlayback decoded: '+video.videoWidth+'×'+video.videoHeight;};
 }catch(e){result.textContent='FAIL: '+e.message;}
};</script></body></html>`;
createServer((req,res)=>{
 if(req.url==='/extract.js'){res.writeHead(200,{'Content-Type':'text/javascript'});res.end(compiled);}
 else if(req.url==='/sample.mp4'){res.writeHead(200,{'Content-Type':'video/mp4','Content-Length':sample.length});res.end(sample);}
 else {res.writeHead(200,{'Content-Type':'text/html'});res.end(html);}
}).listen(4319,'127.0.0.1',()=>console.log('Clip smoke test: http://127.0.0.1:4319'));
