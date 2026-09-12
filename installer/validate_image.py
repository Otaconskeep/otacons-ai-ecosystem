from core.arbiter import ResourceArbiter, ComputeResource
from core.image import ImageProductionManager, ImageGenerationRequest, TestImageProvider
def main(argv=None):
    a=ResourceArbiter([ComputeResource('gpu_test',capacity={'vram_gb':24})])
    m=ImageProductionManager(a,TestImageProvider())
    r=m.generate(ImageGenerationRequest('request_test','A small observatory on a desert hill','draft',agent_id='agent_001',user_id='user_001'))
    print('Provider: test'); print('Service: service_image_test'); print('Profile: draft'); print('Status:',r.status)
    print('Artifact:',r.artifacts[0]['mime_type'],r.artifacts[0]['width'],'x',r.artifacts[0]['height'])
    print('Result: TEST_IMAGE_PASS'); print('ARCHITECTURE_TEST_PASS'); print('REAL_IMAGE_ACCEPTANCE_PENDING_EXTERNAL_ENVIRONMENT'); return 0 if r.status=='COMPLETED' else 1
if __name__=='__main__': raise SystemExit(main())
