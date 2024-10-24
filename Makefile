REGISTRY?=public.ecr.aws/j9g7b3p3/rpkaniko

images-latest:
	aws ecr-public get-login-password --region us-east-1 | docker login --username AWS --password-stdin public.ecr.aws/j9g7b3p3
	sudo docker build --progress=plain --platform=linux/amd64 -f Dockerfile .
	sudo docker push $(REGISTRY)/executor:v2