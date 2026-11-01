import http.server, sys, pathlib
D = pathlib.Path(sys.argv[1])
PAGE = """<html><body><h3>Mock Flow</h3>
<video src="/fx/api/trpc/media.getMediaUrlRedirect?name=old111"></video>
<div contenteditable="true" id="p" style="width:400px;height:40px;border:1px solid"></div>
<button onclick="go()"><span>arrow_forward</span></button>
<script>
function go(){ setTimeout(()=>{ const d=document.createElement('div'); d.setAttribute('role','dialog');
  d.textContent='Spend 20 credits?'; document.body.appendChild(d); }, 500);
 setTimeout(()=>{ const v=document.createElement('video');
  v.src='/fx/api/trpc/media.getMediaUrlRedirect?name=new222'; document.body.appendChild(v);
  window.lastPrompt=document.getElementById('p').innerText; }, 3000); }
</script></body></html>"""
class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if "getMediaUrlRedirect" in self.path:
            name = self.path.split("name=")[1]
            data = (D / ("new.mp4" if name == "new222" else "old.mp4")).read_bytes()
            self.send_response(200); self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        else:
            # Flow's home page (no project open) has no prompt box.
            b = (PAGE.split('<div contenteditable')[0] + "</body></html>" if self.path.endswith("/home")
                 else PAGE).encode(); self.send_response(200); self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[2])), H).serve_forever()
