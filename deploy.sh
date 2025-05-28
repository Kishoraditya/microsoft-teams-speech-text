#!/bin/bash

# Teams Transcription Bot - Production Deployment Script
set -e

echo "🚀 Teams Transcription Bot Deployment Script"
echo "============================================="

# Configuration
PROJECT_NAME="teams-transcription-bot"
RESOURCE_GROUP="${PROJECT_NAME}-rg"
LOCATION="eastus"
CONTAINER_REGISTRY="${PROJECT_NAME}registry"
IMAGE_NAME="${PROJECT_NAME}"
CONTAINER_NAME="${PROJECT_NAME}-container"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check if Azure CLI is installed
    if ! command -v az &> /dev/null; then
        log_error "Azure CLI is not installed. Please install it first."
        exit 1
    fi
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install it first."
        exit 1
    fi
    
    # Check if user is logged in to Azure
    if ! az account show &> /dev/null; then
        log_error "Please login to Azure CLI first: az login"
        exit 1
    fi
    
    # Check if .env file exists
    if [ ! -f ".env" ]; then
        log_error ".env file not found. Please copy .env.template to .env and configure it."
        exit 1
    fi
    
    log_info "Prerequisites check passed ✅"
}

create_azure_resources() {
    log_info "Creating Azure resources..."
    
    # Create resource group
    log_info "Creating resource group: $RESOURCE_GROUP"
    az group create --name $RESOURCE_GROUP --location $LOCATION
    
    # Create container registry
    log_info "Creating container registry: $CONTAINER_REGISTRY"
    az acr create --resource-group $RESOURCE_GROUP --name $CONTAINER_REGISTRY --sku Basic --admin-enabled true
    
    # Create Speech Service
    log_info "Creating Speech Service..."
    az cognitiveservices account create \
        --name "${PROJECT_NAME}-speech" \
        --resource-group $RESOURCE_GROUP \
        --kind SpeechServices \
        --sku S0 \
        --location $LOCATION
    
    # Create Translator Service
    log_info "Creating Translator Service..."
    az cognitiveservices account create \
        --name "${PROJECT_NAME}-translator" \
        --resource-group $RESOURCE_GROUP \
        --kind TextTranslation \
        --sku S1 \
        --location $LOCATION
    
    # Create OpenAI Service
    log_info "Creating OpenAI Service..."
    az cognitiveservices account create \
        --name "${PROJECT_NAME}-openai" \
        --resource-group $RESOURCE_GROUP \
        --kind OpenAI \
        --sku S0 \
        --location $LOCATION
    
    # Create Bot Service
    log_info "Creating Bot Service..."
    az bot create \
        --resource-group $RESOURCE_GROUP \
        --name "${PROJECT_NAME}-bot" \
        --kind registration \
        --endpoint "https://${CONTAINER_NAME}.${LOCATION}.azurecontainer.io/api/messages"
    
    log_info "Azure resources created successfully ✅"
}

build_and_push_image() {
    log_info "Building and pushing Docker image..."
    
    # Get registry login server
    REGISTRY_SERVER=$(az acr show --name $CONTAINER_REGISTRY --resource-group $RESOURCE_GROUP --query loginServer --output tsv)
    
    # Build Docker image
    log_info "Building Docker image..."
    docker build -t ${REGISTRY_SERVER}/${IMAGE_NAME}:latest .
    
    # Login to registry
    log_info "Logging into container registry..."
    az acr login --name $CONTAINER_REGISTRY
    
    # Push image
    log_info "Pushing image to registry..."
    docker push ${REGISTRY_SERVER}/${IMAGE_NAME}:latest
    
    log_info "Image built and pushed successfully ✅"
}

get_service_keys() {
    log_info "Retrieving service keys..."
    
    # Get Speech Service key
    SPEECH_KEY=$(az cognitiveservices account keys list \
        --name "${PROJECT_NAME}-speech" \
        --resource-group $RESOURCE_GROUP \
        --query key1 --output tsv)
    
    # Get Translator Service key
    TRANSLATOR_KEY=$(az cognitiveservices account keys list \
        --name "${PROJECT_NAME}-translator" \
        --resource-group $RESOURCE_GROUP \
        --query key1 --output tsv)
    
    # Get OpenAI Service key
    OPENAI_KEY=$(az cognitiveservices account keys list \
        --name "${PROJECT_NAME}-openai" \
        --resource-group $RESOURCE_GROUP \
        --query key1 --output tsv)
    
    # Get OpenAI endpoint
    OPENAI_ENDPOINT=$(az cognitiveservices account show \
        --name "${PROJECT_NAME}-openai" \
        --resource-group $RESOURCE_GROUP \
        --query properties.endpoint --output tsv)
    
    # Get Bot credentials
    BOT_ID=$(az bot show \
        --resource-group $RESOURCE_GROUP \
        --name "${PROJECT_NAME}-bot" \
        --query microsoftAppId --output tsv)
    
    # Get registry credentials
    REGISTRY_USERNAME=$(az acr credential show \
        --name $CONTAINER_REGISTRY \
        --query username --output tsv)
    
    REGISTRY_PASSWORD=$(az acr credential show \
        --name $CONTAINER_REGISTRY \
        --query passwords[0].value --output tsv)
    
    log_info "Service keys retrieved successfully ✅"
}

deploy_container() {
    log_info "Deploying container to Azure Container Instances..."
    
    REGISTRY_SERVER=$(az acr show --name $CONTAINER_REGISTRY --resource-group $RESOURCE_GROUP --query loginServer --output tsv)
    
    # Create container instance
    az container create \
        --resource-group $RESOURCE_GROUP \
        --name $CONTAINER_NAME \
        --image ${REGISTRY_SERVER}/${IMAGE_NAME}:latest \
        --registry-login-server $REGISTRY_SERVER \
        --registry-username $REGISTRY_USERNAME \
        --registry-password $REGISTRY_PASSWORD \
        --dns-name-label $CONTAINER_NAME \
        --ports 8080 \
        --cpu 2 \
        --memory 4 \
        --environment-variables \
            AZURE_SPEECH_KEY=$SPEECH_KEY \
            AZURE_SPEECH_REGION=$LOCATION \
            AZURE_TRANSLATOR_KEY=$TRANSLATOR_KEY \
            AZURE_TRANSLATOR_REGION=$LOCATION \
            AZURE_OPENAI_KEY=$OPENAI_KEY \
            AZURE_OPENAI_ENDPOINT=$OPENAI_ENDPOINT \
            BOT_ID=$BOT_ID \
            PORT=8080
    
    # Get container FQDN
    CONTAINER_FQDN=$(az container show \
        --resource-group $RESOURCE_GROUP \
        --name $CONTAINER_NAME \
        --query ipAddress.fqdn --output tsv)
    
    log_info "Container deployed successfully ✅"
    log_info "Container URL: https://${CONTAINER_FQDN}"
}

update_bot_endpoint() {
    log_info "Updating bot messaging endpoint..."
    
    CONTAINER_FQDN=$(az container show \
        --resource-group $RESOURCE_GROUP \
        --name $CONTAINER_NAME \
        --query ipAddress.fqdn --output tsv)
    
    az bot update \
        --resource-group $RESOURCE_GROUP \
        --name "${PROJECT_NAME}-bot" \
        --endpoint "https://${CONTAINER_FQDN}/api/messages"
    
    log_info "Bot endpoint updated successfully ✅"
}

setup_teams_channel() {
    log_info "Setting up Teams channel..."
    
    log_info "Please manually enable Teams channel in Azure Portal:"
    log_info "1. Go to Azure Portal -> Bot Services -> ${PROJECT_NAME}-bot"
    log_info "2. Go to Channels -> Add Microsoft Teams channel"
    log_info "3. Configure and save the channel"
    
    log_warn "Teams channel setup requires manual configuration"
}

verify_deployment() {
    log_info "Verifying deployment..."
    
    CONTAINER_FQDN=$(az container show \
        --resource-group $RESOURCE_GROUP \
        --name $CONTAINER_NAME \
        --query ipAddress.fqdn --output tsv)
    
    # Wait for container to be ready
    log_info "Waiting for container to be ready..."
    sleep 30
    
    # Test health endpoint
    if curl -f "https://${CONTAINER_FQDN}/health" > /dev/null 2>&1; then
        log_info "Health check passed ✅"
    else
        log_warn "Health check failed. Check container logs."
    fi
    
    # Show container logs
    log_info "Container logs:"
    az container logs --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME --tail 20
}

cleanup_on_error() {
    log_error "Deployment failed. Cleaning up resources..."
    az group delete --name $RESOURCE_GROUP --yes --no-wait
    log_info "Cleanup initiated"
}

print_summary() {
    log_info "Deployment Summary"
    log_info "=================="
    
    CONTAINER_FQDN=$(az container show \
        --resource-group $RESOURCE_GROUP \
        --name $CONTAINER_NAME \
        --query ipAddress.fqdn --output tsv 2>/dev/null || echo "Not available")
    
    echo ""
    echo "🎉 Deployment completed successfully!"
    echo ""
    echo "📋 Resource Information:"
    echo "   Resource Group: $RESOURCE_GROUP"
    echo "   Container URL: https://${CONTAINER_FQDN}"
    echo "   Bot Name: ${PROJECT_NAME}-bot"
    echo ""
    echo "🔧 Next Steps:"
    echo "   1. Configure Teams channel in Azure Portal"
    echo "   2. Add bot to your Teams workspace"
    echo "   3. Test transcription in a Teams call"
    echo ""
    echo "📝 Useful Commands:"
    echo "   Check logs: az container logs --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME"
    echo "   Restart: az container restart --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME"
    echo "   Delete: az group delete --name $RESOURCE_GROUP"
    echo ""
}

# Main deployment flow
main() {
    echo "Starting deployment process..."
    
    # Set trap for cleanup on error
    trap cleanup_on_error ERR
    
    check_prerequisites
    
    echo ""
    read -p "Do you want to proceed with deployment? (y/N) " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled by user"
        exit 0
    fi
    
    create_azure_resources
    build_and_push_image
    get_service_keys
    deploy_container
    update_bot_endpoint
    setup_teams_channel
    verify_deployment
    print_summary
}

# Parse command line arguments
case "${1:-deploy}" in
    "deploy")
        main
        ;;
    "cleanup")
        log_info "Cleaning up resources..."
        az group delete --name $RESOURCE_GROUP --yes --no-wait
        log_info "Cleanup initiated"
        ;;
    "logs")
        az container logs --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME --follow
        ;;
    "restart")
        log_info "Restarting container..."
        az container restart --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME
        log_info "Container restarted"
        ;;
    "status")
        az container show --resource-group $RESOURCE_GROUP --name $CONTAINER_NAME --query "{Name:name,State:containers[0].instanceView.currentState.state,FQDN:ipAddress.fqdn}" --output table
        ;;
    *)
        echo "Usage: $0 {deploy|cleanup|logs|restart|status}"
        echo ""
        echo "Commands:"
        echo "  deploy  - Deploy the bot (default)"
        echo "  cleanup - Delete all resources"
        echo "  logs    - Show container logs"
        echo "  restart - Restart the container"
        echo "  status  - Show container status"
        exit 1
        ;;
esac