import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator

class TagSchema(BaseModel):
	epc: str = Field('000000000000000000000001')
	tid: Optional[str | None] = Field('E28000000000000000000001')
	ant: Optional[int | None] = 0
	rssi: Optional[int | None] = 0

	@field_validator('epc', 'tid')
	def validate_epc_length_and_hex(cls, v, field):
		if v is None:
			return v
		if len(v) != 24:
			raise ValueError(f'{field} must have exactly 24 characters')
		if not re.fullmatch(r'[0-9a-fA-F]{24}', v):
			raise ValueError(f'{field} must contain only hexadecimal characters (0-9, a-f)')
		return v.lower()
	

class WriteTagValidator(BaseModel):
	target_identifier: Optional[str] = Field(
		None, description='Identifier type: "epc", "tid", or None'
	)
	target_value: Optional[str] = Field(
		None, description='Current value of the identifier (24 hexadecimal characters)'
	)
	new_epc: str = Field(..., description='New EPC value to write (24 hexadecimal characters)')
	password: str = Field(..., description='Password to access the tag (8 hexadecimal characters)')

	@field_validator('target_identifier')
	def validate_identifier(cls, v):
		if v == 'None' or v is None:
			return None
		allowed_values = ('epc', 'tid', None)
		if v not in allowed_values:
			raise ValueError(f'target_identifier must be one of {allowed_values}')
		return v.lower()

	@field_validator('target_value', 'new_epc')
	def validate_epc_length_and_hex(cls, v, field):
		if v is None or v == 'None':
			v = '0' * 24

		if len(v) != 24:
			raise ValueError(f'{field} must have exactly 24 characters')
		if not re.fullmatch(r'[0-9a-fA-F]{24}', v):
			raise ValueError(f'{field} must contain only hexadecimal characters (0-9, a-f)')
		return v.lower()

	@field_validator('password')
	def validate_password_length_and_hex(cls, v, field):
		if len(v) != 8:
			raise ValueError(f'{field} must have exactly 8 characters')
		if not re.fullmatch(r'[0-9a-fA-F]{8}', v):
			raise ValueError(f'{field} must contain only hexadecimal characters (0-9, a-f)')
		return v.lower()
