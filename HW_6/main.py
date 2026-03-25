import os
import json
import tempfile
import boto3
import mimetypes
from botocore.client import Config

def handler(event, context):
    message = event['messages'][0]['details']
    object_key = message['object_id']
    bucket_name = message['bucket_id']
    
    s3 = boto3.client(
        's3',
        endpoint_url='https://storage.yandexcloud.net',
        aws_access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
        aws_secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
        config=Config(signature_version='s3v4')
    )
    
    with tempfile.TemporaryDirectory() as temp_dir:
        local_path = os.path.join(temp_dir, os.path.basename(object_key))
        s3.download_file(bucket_name, object_key, local_path)
        
        content_type, _ = mimetypes.guess_type(os.path.basename(object_key))
        results_key = os.path.basename(object_key)
        data = s3.get_object(Bucket='sdp-uploads', Key=results_key)['Body'].read()
        s3.put_object(
                Bucket='sdp-results',
                Key=results_key,
                Body=data,
                ContentType=content_type
        )
            
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'File processed successfully',
                'result_url': f"https://storage.yandexcloud.net/my-results-bucket/{results_key}"
            })
        }