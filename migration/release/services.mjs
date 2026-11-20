import auth from "./auth.mjs";
import panel from "./dashboard.mjs";

// Request-local adapters keep existing module contracts without remote Workers.
export function createEnvironment(bindings){
 const env={...bindings,SUPABASE_URL:bindings.SUPABASE_URL||"https://hkfyvhthfshnddduckjs.supabase.co"};
 const upstream=bindings.PROD_API||{fetch:request=>auth.fetch(request,env)};
 const identities=new Map();
 env.PROD_API={async fetch(request){
  if(request.method!=='GET'||new URL(request.url).pathname!=='/api/me')return upstream.fetch(request);
  const key=request.headers.get('cookie')||'';
  let pending=identities.get(key);
  if(!pending){pending=Promise.resolve(upstream.fetch(request));identities.set(key,pending);}
  try{const response=await pending;if(!response.ok)identities.delete(key);return response.clone();}
  catch(error){if(identities.get(key)===pending)identities.delete(key);throw error;}
 }};
 env.LEGACY_API=bindings.LEGACY_API||{fetch:request=>panel.fetch(request,env)};
 return env;
}

