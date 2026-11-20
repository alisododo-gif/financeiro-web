// Memory belongs to one authenticated page; never persists personal data.
export function createReadCache(ttl=60000,maxEntries=24,clock=()=>Date.now()){
 const entries=new Map();let epoch=0;
 return {
  clear(){epoch++;entries.clear();},
  async read(key,fetcher){
   const now=clock();for(const [k,e]of entries)if(e.expires<=now)entries.delete(k);
   const old=entries.get(key);if(old)return old.promise;
   const version=epoch,entry={expires:now+ttl,promise:null};
   entry.promise=Promise.resolve().then(fetcher).then(value=>{if(version!==epoch&&entries.get(key)===entry)entries.delete(key);return value;},error=>{if(entries.get(key)===entry)entries.delete(key);throw error;});
   entries.set(key,entry);while(entries.size>maxEntries)entries.delete(entries.keys().next().value);
   return entry.promise;
  }
 };
}

