import logging
import os
import sys
import torch
import time

from .message_define import MyMessage

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../../")))
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../../../FedML")))
try:
    from FedML.fedml_core.distributed.communication.message import Message
    from FedML.fedml_core.distributed.server.server_manager import ServerManager
except ModuleNotFoundError: # except ImportError
    from fedml_core.distributed.communication.message import Message
    from fedml_core.distributed.server.server_manager import ServerManager

from .utils import transform_list_to_tensor
from .utils import transform_tensor_to_list


class BaselineCNNServerManager(ServerManager):
    def __init__(self, args, aggregator, comm=None, rank=0, size=0, backend="MQTT", mqtt_host="127.0.0.1", mqtt_port=1883,is_preprocessed=False,batch_selection=None):
        super().__init__(args, comm, rank, size, backend,mqtt_host,mqtt_port)
        self.args = args
        self.aggregator = aggregator
        self.round_num = args.comm_round
        self.round_idx = 0
        self.is_preprocessed = is_preprocessed
        self.batch_selection = batch_selection
        self.start_time = time.time()

    def run(self):
        super().run()

    def send_init_msg(self):
        global_model_params = self.aggregator.get_global_model_params()
        for process_id in range(1, self.size):
            self.send_message_init_config(process_id, global_model_params)

    def register_message_receive_handlers(self):
        self.register_message_receive_handler(MyMessage.MSG_TYPE_C2S_SEND_MODEL_TO_SERVER,
                                              self.handle_message_receive_model_from_client)

    def handle_message_receive_model_from_client(self, msg_params):
        sender_id = msg_params.get(MyMessage.MSG_ARG_KEY_SENDER)
        cnn_params = msg_params.get(MyMessage.MSG_ARG_KEY_MODEL_PARAMS)
        
        cnn_params = transform_list_to_tensor(cnn_params)
        
        local_sample_number = msg_params.get(MyMessage.MSG_ARG_KEY_NUM_SAMPLES)

        self.aggregator.add_local_trained_result(sender_id - 1, cnn_params, local_sample_number)
        b_all_received = self.aggregator.check_whether_all_receive()
        logging.info("b_all_received = " + str(b_all_received))
        if b_all_received:
            global_model_params = self.aggregator.aggregate()
            self.aggregator.test_on_server_for_all_clients(self.round_idx,self.batch_selection)

            # start the next round
            self.round_idx += 1
            if self.round_idx == self.round_num:
                self.finish()
                return

            print("size = %d" % self.size)
            
            client_indexes = [self.round_idx] * self.args.client_num_per_round
            
            #print time from training star
            print("Time: ", time.time() - self.start_time)

            
            for receiver_id in range(1, self.size):
                self.send_message_sync_model_to_client(receiver_id,
                                                       client_indexes[receiver_id - 1])

    def send_message_init_config(self, receive_id, global_model_params, client_index):
        
        global_model_params = transform_tensor_to_list(global_model_params)

        message = Message(MyMessage.MSG_TYPE_S2C_INIT_CONFIG, self.get_sender_id(), receive_id)
        message.add_params(MyMessage.MSG_ARG_KEY_MODEL_PARAMS, global_model_params)
        message.add_params(MyMessage.MSG_ARG_KEY_CLIENT_INDEX, str(client_index))
        self.send_message(message)

    def send_message_sync_model_to_client(self, receive_id, client_index):
        logging.info("send_message_sync_model_to_client. receive_id = %d" % receive_id)
        
        global_model_params = self.aggregator.get_global_model_params()

        global_model_params = transform_tensor_to_list(global_model_params)

        message = Message(MyMessage.MSG_TYPE_S2C_SYNC_MODEL_TO_CLIENT, self.get_sender_id(), receive_id)
        message.add_params(MyMessage.MSG_ARG_KEY_MODEL_PARAMS, global_model_params)
        message.add_params(MyMessage.MSG_ARG_KEY_CLIENT_INDEX, str(client_index))
        self.send_message(message)
