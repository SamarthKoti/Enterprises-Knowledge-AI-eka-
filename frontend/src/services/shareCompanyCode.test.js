import test from 'node:test';
import assert from 'node:assert/strict';
import {shareCompanyCode} from './shareCompanyCode.js';
test('native share preserves company and leading zeroes',async()=>{
 let payload;
 assert.equal(await shareCompanyCode('Infosys','0007',{share:async value=>{payload=value;}}),'shared');
 assert.match(payload.text,/Infosys employee verification code: 0007/);
 assert.equal(payload.url,undefined);
});
test('unsupported share copies invitation text',async()=>{
 let copied;
 assert.equal(await shareCompanyCode('TCS','0012',{clipboard:{writeText:async text=>{copied=text;}}}),'copied');
 assert.match(copied,/TCS employee verification code: 0012/);
});
test('cancel does not copy or report failure',async()=>{
 assert.equal(await shareCompanyCode('TCS','0012',{share:async()=>{throw Object.assign(new Error('cancel'),{name:'AbortError'});},clipboard:{writeText:()=>assert.fail('Unexpected copy')}}),'cancelled');
});
test('share and clipboard failures are surfaced',async()=>{
 await assert.rejects(shareCompanyCode('TCS','0012',{share:async()=>{throw new Error('denied');}}),/denied/);
 await assert.rejects(shareCompanyCode('TCS','0012',{clipboard:{writeText:async()=>{throw new Error('blocked');}}}),/blocked/);
});
