from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from .models import Data
from .serializers import DataSerializer
from django_filters.rest_framework import DjangoFilterBackend
from .filters import DataFilter
from rest_framework.response import Response
from rest_framework import status
from openai import OpenAI
from django.conf import settings
client = OpenAI(api_key=settings.OPEN_AI_API_KEY)

class DataViewSet(viewsets.ModelViewSet):
    queryset = Data.objects.all()
    serializer_class = DataSerializer
    filter_backends = [filters.SearchFilter, DjangoFilterBackend]
    filterset_class = DataFilter
    search_fields = ['group_id']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        if not queryset.exists():
            return Response({"Error": "一致する検索結果がありません"}, status=status.HTTP_404_NOT_FOUND)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def generate_scenario(self, request):
        transcript = request.data.get('transcript')
        if not transcript:
            return Response({'error': 'Transcript is required.'}, status=status.HTTP_400_BAD_REQUEST)

        prompt = ("#命令文:\nあなたは優秀な教員です。以降に示す会話の一部を見て、このグループに対してどのように声を掛け指導を開始しますか？指導の際の声掛けシナリオを箇条書きで複数提示してください。\n" + "#グループワークの内容:\n" + transcript)


        try:
            completion = client.chat.completions.create(model='gpt-4o-mini',
            messages=[
                {"role": "user", "content": prompt}
            ])
            generated_scenario = completion.choices[0].message.content
            return Response({'scenario': generated_scenario}, status=status.HTTP_200_OK)
        except Exception as e:
            print('Error generating scenario:', str(e))
            return Response({'error': 'Failed to generate scenario.'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)