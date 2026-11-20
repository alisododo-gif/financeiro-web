import test from 'node:test';import assert from 'node:assert/strict';
import {createReadCache} from './read-cache.mjs';
test('reads share requests, expire, and separate month/module keys',async()=>{
 let now=0,calls=0;const c=createReadCache(60,24,()=>now),read=()=>Promise.resolve(++calls);
 assert.deepEqual(await Promise.all([c.read('owner:1:out:launch',read),c.read('owner:1:out:launch',read)]),[1,1]);
 assert.equal(await c.read('owner:1:nov:launch',read),2);assert.equal(await c.read('owner:1:out:cards',read),3);
 now=61;assert.equal(await c.read('owner:1:out:launch',read),4);
});
test('logout or mutation cannot let a late response replace a new session read',async()=>{
 const c=createReadCache();let finish;const old=c.read('same',()=>new Promise(r=>finish=r));await Promise.resolve();
 c.clear();assert.equal(await c.read('same',async()=>2),2);finish(1);assert.equal(await old,1);
 assert.equal(await c.read('same',async()=>3),2);
});
test('failed reads are retried and cache remains bounded',async()=>{
 const c=createReadCache(60000,2);await assert.rejects(c.read('a',async()=>{throw Error('offline');}));assert.equal(await c.read('a',async()=>1),1);
 await c.read('b',async()=>2);await c.read('c',async()=>3);assert.equal(await c.read('a',async()=>4),4);
});
