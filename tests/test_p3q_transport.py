import importlib.util
import json
import os
from pathlib import Path
import unittest

os.environ['JETBASE_P3Q_TRANSPORT_KEY']='local-scoped-transport-test'
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('cirq_service', ROOT/'main.py')
service=importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)
from fastapi.testclient import TestClient

class TransportTests(unittest.TestCase):
    def test_actual_cap22_measurements_and_native_handoff(self):
        client=TestClient(service.app)
        auth={'x-aura-bridge-key':'local-scoped-transport-test'}
        self.assertEqual(client.post('/cap22/statevector',json={'message':'READY'}).status_code,403)
        self.assertEqual(client.post('/intake/gguf',json={}).status_code,403)
        response=client.post('/cap22/statevector',json={'message':'READY'},headers=auth)
        self.assertEqual(response.status_code,200)
        cap=response.json()
        self.assertEqual(cap['active_qubits'],22)
        self.assertEqual(cap['statevector_amplitudes'],2**22)
        self.assertEqual(sum(cap['counts'].values()),64)
        self.assertAlmostEqual(cap['statevector_norm'],1,places=4)
        for i,probability in enumerate(cap['six_data_marginals']):
            self.assertEqual(probability,sum(n for bits,n in cap['counts'].items() if bits[i]=='1')/64)
        packet={'oracle':{'listener_port':14700},'gguf':[{'seat':'phi2','function':'actual transport test output'}],'cap22':cap,'position':{'lane_id':160,'coordinates':[1499,1499,1499]}}
        calls=[]
        original=service._call_backend
        def backend(path,method,payload,timeout):
            calls.append((path,method,payload,timeout))
            return 200,{'ok':True,'coins':[{'receipt':{'receipt_hash':'a'*64,'evaluation_complete':True,'committed':False,'status':'HOLD'}}]}
        try:
            service._call_backend=backend
            response=client.post('/intake/gguf',json=packet,headers=auth)
            self.assertEqual(response.status_code,200)
            result=response.json()
            self.assertEqual(result['committed'],False)
            self.assertEqual(result['receipts'][0]['status'],'HOLD')
            self.assertEqual(calls[0][0],'/qhp/decoherence-fuel/fire')
            self.assertEqual(calls[0][2]['body'],cap['six_data_marginals'])
            self.assertEqual(result['gguf'],packet['gguf'])
            packet['cap22']['six_data_marginals'][0]=float('inf')
            request=client.post('/intake/gguf',content=json.dumps(packet),headers={**auth,'Content-Type':'application/json'})
            self.assertEqual(request.status_code,400)
            self.assertEqual(len(calls),1)
        finally:service._call_backend=original

if __name__=='__main__':unittest.main()
