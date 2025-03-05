from solana.rpc.api import Client
from solana.account import Account
from solana.publickey import PublicKey
from solana.transaction import Transaction, TransactionInstruction
from solana.system_program import transfer, TransferParams
from spl.token.client import Token
from spl.token.constants import TOKEN_PROGRAM_ID
import base58

class SolanaClient:
    def __init__(self, endpoint="https://api.mainnet-beta.solana.com"):  #  endpoint
        self.client = Client(endpoint)

    def create_wallet(self) -> dict:
        """Создает новый кошелек Solana."""
        account = Account()
        private_key = base58.b58encode(account.keypair()).decode('utf-8')
        address = str(account.public_key())
        return {'address': address, 'private_key': private_key}

    def get_balance(self, address: str, token_address: str = None) -> float:
        """Возвращает баланс кошелька.

        Args:
            address: Адрес кошелька.
            token_address: Адрес контракта токена (если None, то возвращается баланс SOL).
        """
        try:
            public_key = PublicKey(address)

            if token_address is None:
                # Баланс SOL
                balance_response = self.client.get_balance(public_key)
                balance = balance_response['result']['value'] / (10 ** 9)  # Lamports to SOL
            else:
                # Баланс токена (SPL)
                token_public_key = PublicKey(token_address)
                token = Token(self.client, token_public_key, TOKEN_PROGRAM_ID, None)  #  payer

                #  associated token account
                try:
                    account_info = token.get_accounts_by_owner(public_key, commitment="processed")['result']['value']
                    if not account_info:
                        return 0.0
                    #  берем первый попавшийся,  нужно обрабатывать несколько
                    token_account = account_info[0]['pubkey']
                    balance_info = token.get_balance(token_account, commitment="processed")
                    balance = balance_info['result']['value']['uiAmount'] # используем uiAmount

                except Exception as e:
                    print(f"Error getting token balance: {e}")
                    return 0.0

            return balance

        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0.0

    def transfer(self, sender_private_key: str, recipient_address: str, amount: float, token_address: str = None) -> dict:
        """Переводит SOL или SPL токены."""
        try:
            sender_account = Account(base58.b58decode(sender_private_key))
            recipient_public_key = PublicKey(recipient_address)

            transaction = Transaction()

            if token_address is None:
                # Перевод SOL
                transfer_params = TransferParams(
                    from_pubkey=sender_account.public_key(),
                    to_pubkey=recipient_public_key,
                    lamports=int(amount * (10 ** 9))  # SOL to Lamports
                )
                transaction.add(transfer(transfer_params))
            else:
                # Перевод SPL токена
                token_public_key = PublicKey(token_address)
                token = Token(self.client, token_public_key, TOKEN_PROGRAM_ID, sender_account) # payer

                #  associated token accounts
                sender_token_account = token.get_accounts_by_owner(sender_account.public_key())['result']['value'][0]['pubkey'] #  первый
                recipient_token_account = token.get_accounts_by_owner(recipient_public_key)['result']['value'][0]['pubkey']

                #  инструкцию
                transfer_instruction = token.transfer(
                    source=sender_token_account,
                    dest=recipient_token_account,
                    owner=sender_account.public_key(),
                    amount=int(amount * (10 ** token.get_mint_info()['result']['value']['decimals'])), #  decimals
                    signers=[]
                )
                transaction.add(transfer_instruction)

            result = self.client.send_transaction(transaction, sender_account)
            return {'success': True, 'transaction_id': result['result']}

        except Exception as e:
            print(f"Error transferring funds: {e}")
            return {'success': False, 'error': str(e)} 