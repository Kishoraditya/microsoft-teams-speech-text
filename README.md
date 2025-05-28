# Teams Live Transcription & Translation Bot

A production-ready Teams bot that provides live transcription of Sinhala speech and real-time translation to English during Microsoft Teams calls.

## Features

- **Live Transcription**: Real-time speech-to-text for Sinhala language
- **Instant Translation**: Automatic translation from Sinhala to English
- **Teams Integration**: Seamless integration with Microsoft Teams calls
- **Production Ready**: Dockerized deployment with health checks
- **Configurable**: All settings via environment variables

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Azure subscription with the following services:
  - Azure Speech Service
  - Azure Translator Service
  - Azure OpenAI Service
  - Azure Bot Service

### 1. Clone and Setup

```bash
# Clone the repository
git clone <your-repo-url>
cd teams-transcription-bot

# Copy environment template
cp .env.template .env
```

### 2. Configure Environment Variables

Edit `.env` file with your Azure service keys:

```bash
# Get Azure Speech Service key
az cognitiveservices account keys list --name <your-speech-service-name> --resource-group <your-rg>

# Get Azure Translator key
az cognitiveservices account keys list --name <your-translator-service-name> --resource-group <your-rg>

# Get Azure OpenAI key
az cognitiveservices account keys list --name <your-openai-service-name> --resource-group <your-rg>
```

### 3. Deploy with Docker

```bash
# Build and run
docker-compose up -d

# Check logs
docker-compose logs -f

# Health check
curl http://localhost:8080/health
```

### 4. Register Teams Bot

1. Go to [Azure Portal](https://portal.azure.com)
2. Create a new **Bot Channels Registration**
3. Set messaging endpoint to: `https://your-domain.com/api/messages`
4. Enable Teams channel
5. Update `.env` with `BOT_ID` and `BOT_PASSWORD`

## Production Deployment

### Azure Container Instances

```bash
# Create resource group
az group create --name teams-bot-rg --location eastus

# Create container instance
az container create \
  --resource-group teams-bot-rg \
  --name teams-transcription-bot \
  --image <your-registry>/teams-bot:latest \
  --ports 8080 \
  --environment-variables \
    AZURE_SPEECH_KEY=$AZURE_SPEECH_KEY \
    AZURE_SPEECH_REGION=$AZURE_SPEECH_REGION \
    AZURE_TRANSLATOR_KEY=$AZURE_TRANSLATOR_KEY \
    AZURE_TRANSLATOR_REGION=$AZURE_TRANSLATOR_REGION \
    AZURE_OPENAI_KEY=$AZURE_OPENAI_KEY \
    AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT \
    BOT_ID=$BOT_ID \
    BOT_PASSWORD=$BOT_PASSWORD
```

### Azure App Service

```bash
# Create App Service plan
az appservice plan create \
  --name teams-bot-plan \
  --resource-group teams-bot-rg \
  --sku B1 \
  --is-linux

# Create web app
az webapp create \
  --resource-group teams-bot-rg \
  --plan teams-bot-plan \
  --name teams-transcription-bot \
  --deployment-container-image-name <your-registry>/teams-bot:latest

# Configure app settings
az webapp config appsettings set \
  --resource-group teams-bot-rg \
  --name teams-transcription-bot \
  --settings @appsettings.json
```

### Kubernetes

```bash
# Create namespace
kubectl create namespace teams-bot

# Create secret from .env
kubectl create secret generic teams-bot-config \
  --from-env-file=.env \
  --namespace=teams-bot

# Apply deployment
kubectl apply -f kubernetes.yaml
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/messages` | POST | Teams webhook endpoint |
| `/api/sessions/{id}` | GET | Get session transcriptions |
| `/health` | GET | Health check |

## Usage

### In Teams Chat

1. Add the bot to your Teams channel
2. Start a call
3. Type: `@TranscriptionBot start transcription`
4. Speak in Sinhala during the call
5. Real-time transcriptions will appear in chat
6. Type: `@TranscriptionBot stop transcription` to stop

### Programmatic API

```python
import requests

# Get session data
response = requests.get('http://localhost:8080/api/sessions/session_id')
transcriptions = response.json()

# Health check
health = requests.get('http://localhost:8080/health')
print(health.json())
```

## Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `AZURE_SPEECH_KEY` | Azure Speech Service key | Yes |
| `AZURE_SPEECH_REGION` | Azure region | Yes |
| `AZURE_TRANSLATOR_KEY` | Azure Translator key | Yes |
| `AZURE_TRANSLATOR_REGION` | Azure region | Yes |
| `AZURE_OPENAI_KEY` | Azure OpenAI key | Yes |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint | Yes |
| `BOT_ID` | Teams bot ID | Yes |
| `BOT_PASSWORD` | Teams bot password | Yes |
| `PORT` | Server port | No (default: 8080) |
| `LOG_LEVEL` | Logging level | No (default: INFO) |

### Azure Service Setup

#### Speech Service

```bash
az cognitiveservices account create \
  --name speech-service \
  --resource-group teams-bot-rg \
  --kind SpeechServices \
  --sku S0 \
  --location eastus
```

#### Translator Service

```bash
az cognitiveservices account create \
  --name translator-service \
  --resource-group teams-bot-rg \
  --kind TextTranslation \
  --sku S1 \
  --location eastus
```

#### OpenAI Service

```bash
az cognitiveservices account create \
  --name openai-service \
  --resource-group teams-bot-rg \
  --kind OpenAI \
  --sku S0 \
  --location eastus
```

## Monitoring

### Logs

```bash
# Docker logs
docker-compose logs -f teams-transcription-bot

# Kubernetes logs
kubectl logs -f deployment/teams-transcription-bot -n teams-bot

# Azure Container Instances logs
az container logs --resource-group teams-bot-rg --name teams-transcription-bot
```

### Metrics

```bash
# Health check
curl http://localhost:8080/health

# Session stats
curl http://localhost:8080/api/sessions/stats
```

## Troubleshooting

### Common Issues

1. **Bot not responding in Teams**
   - Check bot registration messaging endpoint
   - Verify bot ID and password in `.env`
   - Check Azure Bot Service configuration

2. **Audio transcription not working**
   - Verify Azure Speech Service key and region
   - Check microphone permissions in Teams
   - Ensure Sinhala language is supported

3. **Translation errors**
   - Verify Azure Translator key and region
   - Check network connectivity to Azure services
   - Review logs for API errors

### Debug Mode

```bash
# Run with debug logging
LOG_LEVEL=DEBUG docker-compose up

# Test individual components
python -c "from teams_bot import TeamsTranscriptionBot; bot = TeamsTranscriptionBot()"
```

## Development

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run locally
python teams_bot.py
```

### Testing

```bash
# Unit tests
pytest tests/

# Integration tests
pytest tests/integration/

# Load testing
locust -f tests/load_test.py
```

## Security

- All sensitive data is stored in environment variables
- Bot uses Azure AD authentication
- HTTPS endpoints required for production
- Regular security updates via automated builds

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:

- Create GitHub issue
- Check Azure service status
- Review Azure documentation

## Contributing

1. Fork the repository
2. Create feature branch
3. Add tests for new functionality
4. Submit pull request

---

**Note**: This bot requires appropriate Azure service quotas and may incur costs based on usage. Monitor your Azure billing regularly.

## 📁 **Complete File Structure**

- **`teams_bot.py`** - Single main bot file with all functionality
- **`requirements.txt`** - Python dependencies
- **`.env.template`** - Configuration template
- **`Dockerfile`** - Container configuration
- **`docker-compose.yml`** - Local deployment
- **`deploy.sh`** - Automated production deployment script
- **`README.md`** - Complete documentation

## 🚀 **Quick Start (3 Commands)**

```bash
# 1. Setup
cp .env.template .env
# Edit .env with your Azure keys

# 2. Test locally
docker-compose up -d

# 3. Deploy to production
chmod +x deploy.sh
./deploy.sh
```

## ✨ **Key Features**

- **Live Transcription**: Real-time Sinhala speech-to-text
- **Instant Translation**: Sinhala → English translation
- **Teams Integration**: Works directly in Teams calls
- **Production Ready**: Full Azure deployment with monitoring
- **Single File**: Everything in one Python file for simplicity
- **Auto-Deploy**: Complete infrastructure setup script

## 🔧 **Architecture**

The bot uses:

- **Azure Speech Service** for Sinhala transcription
- **Azure Translator** for translation to English
- **Azure OpenAI** for enhanced processing
- **Azure Container Instances** for hosting
- **Teams Bot Framework** for integration

## 📋 **What the deploy.sh does:**

1. Creates all Azure resources (Speech, Translator, OpenAI, Bot Service)
2. Builds and pushes Docker image to Azure Container Registry
3. Deploys to Azure Container Instances
4. Configures bot messaging endpoint
5. Provides setup instructions for Teams channel

## 💰 **Cost Estimate**

- Speech Service: ~$1-4/hour of transcription
- Translator: ~$10/million characters
- Container Instance: ~$30-50/month
- OpenAI: ~$0.002/1K tokens

## 🛠 **Management Commands**

```bash
./deploy.sh deploy   # Full deployment
./deploy.sh cleanup  # Delete everything
./deploy.sh logs     # View logs
./deploy.sh restart  # Restart container
./deploy.sh status   # Check status
```

 The bot will automatically join Teams calls, transcribe Sinhala speech in real-time, translate to English, and post results in the chat.
