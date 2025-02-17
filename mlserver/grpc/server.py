from grpc import aio
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Tuple

from ..handlers import DataPlane, ModelRepositoryHandlers
from ..settings import Settings

from .servicers import InferenceServicer, ModelRepositoryServicer
from .dataplane_pb2_grpc import add_GRPCInferenceServiceServicer_to_server
from .model_repository_pb2_grpc import add_ModelRepositoryServiceServicer_to_server
from .interceptors import LoggingInterceptor
from .logging import logger

# Workers used for non-AsyncIO workloads (which aren't any in our case)
DefaultGrpcWorkers = 5


class GRPCServer:
    def __init__(
        self,
        settings: Settings,
        data_plane: DataPlane,
        model_repository_handlers: ModelRepositoryHandlers,
    ):
        self._settings = settings
        self._data_plane = data_plane
        self._model_repository_handlers = model_repository_handlers

    def _create_server(self):
        self._inference_servicer = InferenceServicer(self._data_plane)
        self._model_repository_servicer = ModelRepositoryServicer(
            self._model_repository_handlers
        )

        logging_interceptor = LoggingInterceptor()
        self._server = aio.server(
            ThreadPoolExecutor(max_workers=DefaultGrpcWorkers),
            interceptors=(logging_interceptor,),
            options=self._get_options(),
        )

        add_GRPCInferenceServiceServicer_to_server(
            self._inference_servicer, self._server
        )
        add_ModelRepositoryServiceServicer_to_server(
            self._model_repository_servicer, self._server
        )

        self._server.add_insecure_port(
            f"{self._settings.host}:{self._settings.grpc_port}"
        )

        return self._server

    def _get_options(self) -> List[Tuple[str, Any]]:
        options = []

        max_message_length = self._settings.grpc_max_message_length
        if max_message_length is not None:
            options += [
                ("grpc.max_message_length", max_message_length),
                ("grpc.max_send_message_length", max_message_length),
                ("grpc.max_receive_message_length", max_message_length),
            ]

        return options

    async def start(self):
        self._create_server()

        await self._server.start()

        logger.info(
            "gRPC server running on "
            f"http://{self._settings.host}:{self._settings.grpc_port}"
        )
        await self._server.wait_for_termination()

    async def stop(self):
        # TODO: Read from config
        await self._server.stop(grace=5)
