import test from 'node:test';
import assert from 'node:assert/strict';
import {selectedEvidenceMessage} from './evidence.js';
const older={id:'older',result:{citations:[{chunk_id:'old-source'}]}};
const newer={id:'newer',result:{citations:[{chunk_id:'new-source'}]}};
test('selected older response keeps its own citations after a new answer arrives',()=>{
 assert.equal(selectedEvidenceMessage([older,newer],'older'),older);
});
test('new pending, failed, or uncovered response never inherits old citations',()=>{
 for(const latest of [{id:'newer'},{id:'newer',error:'failed'},{id:'newer',result:{citations:[]}}]){
  assert.equal(selectedEvidenceMessage([older,latest],'newer'),latest);
  assert.equal(selectedEvidenceMessage([older,latest],null),latest);
 }
});
test('missing selection and empty history never fall back to unrelated sources',()=>{
 assert.equal(selectedEvidenceMessage([older],'removed'),undefined);
 assert.equal(selectedEvidenceMessage([],null),undefined);
});
