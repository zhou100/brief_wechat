"""
Test categorization functionality
"""
import pytest
pytest.skip("Legacy utils.categorization tests superseded by app.services.categorization tests", allow_module_level=True)
import os
import json
import logging
from unittest.mock import Mock, patch, AsyncMock
from collections import namedtuple
from app.utils.categorization import CategoryType, get_categorization_service, CategorizationService
from openai import OpenAI, OpenAIError

logging.basicConfig(level=logging.DEBUG, force=True)
logger = logging.getLogger(__name__)

# Create namedtuple classes for response structure
Message = namedtuple('Message', ['content', 'role'])
Choice = namedtuple('Choice', ['message', 'index', 'finish_reason'])
Response = namedtuple('Response', ['choices', 'model'])

@pytest.fixture
def mock_openai():
    with patch('app.utils.categorization.OpenAI') as mock_client:
        # Create a mock instance with the required structure
        instance = Mock()
        
        # Mock models with list method
        instance.models = Mock()
        instance.models.list = Mock(return_value=[{"id": "gpt-4o-mini"}])
        
        # Mock chat completions
        instance.chat = Mock()
        instance.chat.completions = Mock()
        instance.chat.completions.create = AsyncMock()  # Use AsyncMock for async method
        
        # Configure the mock class to return our instance
        mock_client.return_value = instance
        
        yield mock_client

@pytest.fixture
def create_mock_response():
    def _create_mock_response(content):
        # Create a response with proper namedtuple structure
        message = Message(
            content=content if isinstance(content, str) else json.dumps({"categories": content}),
            role='assistant'
        )
        choice = Choice(message=message, index=0, finish_reason='stop')
        response = Response(choices=[choice], model='gpt-4o-mini')
        return response
    return _create_mock_response

@pytest.fixture
async def service(mock_openai):
    service = CategorizationService()
    service._validate_api_key = Mock()
    service.client = mock_openai.return_value
    return service

class TestCategoryTypeEnum:
    def test_category_type_enum(self):
        assert CategoryType.TODO.value == "TODO"
        assert CategoryType.EXPERIMENT.value == "EXPERIMENT"
        assert CategoryType.REFLECTION.value == "REFLECTION"
        assert CategoryType.TIME_RECORD.value == "TIME_RECORD"

class TestServiceInitialization:
    def test_initialization_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="OPENAI_API_KEY environment variable is not set"):
                get_categorization_service()

    def test_initialization_with_invalid_api_key(self, mock_openai):
        mock_openai.return_value.models.list.side_effect = OpenAIError("Invalid API key")
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'invalid-key'}):
            with pytest.raises(Exception, match="Failed to validate API key"):
                get_categorization_service()

    def test_successful_initialization(self, service):
        assert service is not None
        assert hasattr(service, 'client')

class TestTextCategorization:
    @pytest.mark.asyncio
    async def test_categorize_text_success(self, service, mock_openai, create_mock_response):
        # Create mock response
        mock_response = create_mock_response([{"category": "TODO", "extracted_content": "buy groceries tomorrow"}])
        service.client.chat.completions.create.return_value = mock_response
        
        # Call the method
        categories = await service.categorize_text("Test input")
        
        # Verify the result
        assert isinstance(categories, list)
        assert len(categories) == 1
        
        category = categories[0]
        assert "category" in category
        assert "extracted_content" in category
        assert category["category"] == "TODO"
        assert "buy groceries" in category["extracted_content"].lower()
        assert "tomorrow" in category["extracted_content"].lower()
        
        # Verify the API call
        service.client.chat.completions.create.assert_called_once_with(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": service._get_system_prompt()},
                {"role": "user", "content": service._get_user_prompt("Test input")}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

    @pytest.mark.asyncio
    async def test_categorize_text_api_error(self, service, mock_openai):
        service.client.chat.completions.create.side_effect = OpenAIError("API Error")
        text = "test text for api error"
        
        with pytest.raises(Exception, match="Failed to categorize text"):
            await service.categorize_text(text)

    @pytest.mark.asyncio
    async def test_empty_categories_response(self, service, mock_openai, create_mock_response):
        mock_response = create_mock_response([])
        service.client.chat.completions.create.return_value = mock_response
        
        categories = await service.categorize_text("text without any categories")
        assert isinstance(categories, list)
        assert len(categories) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("invalid_content,expected_error", [
        ("invalid json content", "Failed to parse API response"),
        ('{"wrong_key": "wrong value"}', "Failed to categorize text: Categories field is missing or not a list"),
        ('{"categories": 123}', "Failed to categorize text: Categories field is missing or not a list"),
        ('{"categories": null}', "Failed to categorize text: Categories field is missing or not a list"),
        ('{"categories": "not a list"}', "Failed to categorize text: Categories field is missing or not a list")
    ])
    async def test_response_format_validation(self, service, mock_openai, invalid_content, expected_error):
        # Create a mock response with invalid content directly
        mock_response = Mock()
        mock_choice = Mock()
        mock_message = Mock()
        mock_message.content = invalid_content
        mock_message.role = 'assistant'
        mock_choice.message = mock_message
        mock_choice.index = 0
        mock_choice.finish_reason = 'stop'
        mock_response.choices = [mock_choice]
        mock_response.model = 'gpt-4o-mini'
        service.client.chat.completions.create.return_value = mock_response
        
        with pytest.raises(Exception, match=expected_error):
            await service.categorize_text("test text for format validation")

    @pytest.mark.asyncio
    async def test_multiple_categories_response(self, service, mock_openai, create_mock_response):
        content = [
            {"category": "TODO", "extracted_content": "buy groceries tomorrow and call mom"},
            {"category": "EXPERIMENT", "extracted_content": "experiment for a new project"}
        ]
        mock_response = create_mock_response(content)
        service.client.chat.completions.create.return_value = mock_response
        
        categories = await service.categorize_text("test text with multiple categories")
        
        assert isinstance(categories, list)
        assert len(categories) == 2
        
        todo_category = next((cat for cat in categories if cat["category"] == "TODO"), None)
        assert todo_category is not None
        assert "buy groceries" in todo_category["extracted_content"].lower()
        assert "call mom" in todo_category["extracted_content"].lower()
        
        experiment_category = next((cat for cat in categories if cat["category"] == "EXPERIMENT"), None)
        assert experiment_category is not None
        assert "experiment" in experiment_category["extracted_content"].lower()
        assert "project" in experiment_category["extracted_content"].lower()

class TestPromptFormatting:
    def test_system_prompt_format(self, service):
        prompt = service._get_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "JSON" in prompt
        assert "categories" in prompt

    def test_user_prompt_format(self, service):
        text = "Example text"
        prompt = service._get_user_prompt(text)
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert text in prompt

class TestGPTConfiguration:
    @pytest.mark.asyncio
    async def test_gpt_model_name(self, service, mock_openai, create_mock_response):
        mock_response = create_mock_response([{"category": "TODO", "extracted_content": "Test task"}])
        service.client.chat.completions.create.return_value = mock_response
        
        await service.categorize_text("Test input")
        
        service.client.chat.completions.create.assert_called_once_with(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": service._get_system_prompt()},
                {"role": "user", "content": service._get_user_prompt("Test input")}
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )

@pytest.mark.asyncio
class TestTranscribedAudioExamples:
    @pytest.mark.parametrize("example", [
        {"text": "I need to buy groceries tomorrow and also remember to call mom", "expected_category": "TODO"},
        {"text": "I had a great experiment to try for a new app that helps people track their daily tasks", "expected_category": "EXPERIMENT"},
        {"text": "I spent 2 hours working on the project documentation today", "expected_category": "TIME_RECORD"},
        {"text": "I've been reflecting on how technology affects our daily lives", "expected_category": "REFLECTION"}
    ])
    async def test_transcribed_audio_examples(self, service, mock_openai, create_mock_response, example):
        mock_response = create_mock_response([{"category": example["expected_category"], "extracted_content": example["text"]}])
        service.client.chat.completions.create.return_value = mock_response
        
        categories = await service.categorize_text(example["text"])
        
        assert isinstance(categories, list)
        assert len(categories) == 1
        actual_category = categories[0]
        assert actual_category["category"] == example["expected_category"]
        assert isinstance(actual_category["extracted_content"], str)
        assert len(actual_category["extracted_content"]) > 0

class TestLoggingOutput:
    @pytest.mark.asyncio
    async def test_logging_output(self, service, mock_openai, caplog, create_mock_response):
        caplog.set_level(logging.DEBUG)
        
        mock_response = create_mock_response([{"category": "REFLECTION", "extracted_content": "test text"}])
        service.client.chat.completions.create.return_value = mock_response
        
        text = "test text for logging"
        await service.categorize_text(text)
        
        assert any("Categorizing text" in record.message for record in caplog.records)
        assert any("Raw API response content" in record.message for record in caplog.records)
        assert any("Categorization successful" in record.message for record in caplog.records)
